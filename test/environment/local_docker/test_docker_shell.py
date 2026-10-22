"""Unit tests for privilege removal before the container shell starts."""

import importlib.util
import logging
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import Mock, call, patch

import pytest

from microbots.environment.local_docker import image_builder


pytestmark = pytest.mark.unit


@pytest.fixture
def shell_runtime(monkeypatch):
    builder = Path(image_builder.__file__).parent
    runtime = Mock()
    runtime.geteuid.return_value = 0
    for name in ("geteuid", "setgroups", "setgid", "setuid"):
        monkeypatch.setattr(os, name, getattr(runtime, name))
    monkeypatch.setattr(subprocess, "run", runtime.run)

    with patch.dict(os.environ), patch("logging.basicConfig") as configure_logging:
        for name in ("AGENT_UID", "AGENT_GID", "BOT_WORKDIR"):
            monkeypatch.delenv(name, raising=False)
        os.environ.update(HOME="/root", USER="root", LOGNAME="root")

        # Load the real communicator to cover its logging configuration, but
        # replace shell creation so no subprocesses or threads are started.
        spec = importlib.util.spec_from_file_location(
            "ShellCommunicator", builder / "ShellCommunicator.py"
        )
        communicator = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, "ShellCommunicator", communicator)
        spec.loader.exec_module(communicator)
        monkeypatch.setattr(communicator, "ShellCommunicator", runtime.shell)

        yield lambda: runpy.run_path(str(builder / "dockerShell.py")), runtime, configure_logging


def test_communicator_logs_to_agent_owned_directory(shell_runtime):
    _, _, configure_logging = shell_runtime

    configure_logging.assert_called_once_with(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename="/var/log/microbots/ShellCommunicator.log",
    )


@pytest.mark.parametrize(
    "uid, gid, workdir, expected_uid, expected_gid",
    [
        (None, None, None, 1001, 1001),
        ("", "", "", 1001, 1001),
        ("1001", "1001", None, 1001, 1001),
        ("2001", "2002", "/work dir", 2001, 2002),
        ("1001", "2002", None, 1001, 2002),
    ],
)
def test_root_startup_drops_privileges_before_starting_shell(
    shell_runtime, monkeypatch, uid, gid, workdir, expected_uid, expected_gid
):
    load_shell, runtime, _ = shell_runtime
    for name, value in (("AGENT_UID", uid), ("AGENT_GID", gid), ("BOT_WORKDIR", workdir)):
        if value is not None:
            monkeypatch.setenv(name, value)

    load_shell()

    expected_calls = [call.geteuid()]
    if (expected_uid, expected_gid) != (1001, 1001):
        expected_calls.extend([
            call.run(["groupmod", "-g", str(expected_gid), "agent"], check=True),
            call.run(
                ["usermod", "-u", str(expected_uid), "-g", str(expected_gid), "agent"],
                check=True,
            ),
        ])
    paths = ["/home/agent", "/var/log/microbots"]
    if workdir:
        paths.append(workdir)
    expected_calls.extend(
        call.run(["chown", "-R", f"{expected_uid}:{expected_gid}", path], check=False)
        for path in paths
    )
    expected_calls.extend([
        call.setgroups([expected_gid]),
        call.setgid(expected_gid),
        call.setuid(expected_uid),
        call.shell("bash"),
        call.shell().start_session(),
    ])
    assert runtime.mock_calls == expected_calls
    assert os.environ["HOME"] == "/home/agent"
    assert os.environ["USER"] == os.environ["LOGNAME"] == "agent"


def test_non_root_startup_preserves_identity(shell_runtime):
    load_shell, runtime, _ = shell_runtime
    runtime.geteuid.return_value = 1001
    os.environ.update(HOME="/home/existing", USER="existing", LOGNAME="existing")

    load_shell()

    assert runtime.mock_calls == [
        call.geteuid(),
        call.shell("bash"),
        call.shell().start_session(),
    ]
    assert os.environ["HOME"] == "/home/existing"
    assert os.environ["USER"] == os.environ["LOGNAME"] == "existing"


@pytest.mark.parametrize("operation", ["setgroups", "setgid", "setuid"])
def test_privilege_drop_failure_prevents_shell_start(shell_runtime, operation):
    load_shell, runtime, _ = shell_runtime
    getattr(runtime, operation).side_effect = PermissionError("cannot drop privileges")

    with pytest.raises(PermissionError, match="cannot drop privileges"):
        load_shell()

    runtime.shell.assert_not_called()


def test_identity_alignment_failure_prevents_shell_start(shell_runtime, monkeypatch):
    load_shell, runtime, _ = shell_runtime
    monkeypatch.setenv("AGENT_UID", "2001")
    runtime.run.side_effect = subprocess.CalledProcessError(1, "groupmod")

    with pytest.raises(subprocess.CalledProcessError):
        load_shell()

    runtime.setgroups.assert_not_called()
    runtime.setgid.assert_not_called()
    runtime.setuid.assert_not_called()
    runtime.shell.assert_not_called()
