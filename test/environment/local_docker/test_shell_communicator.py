"""Tests that the container shell survives the commands an agent may send it."""

import importlib.util
import io
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from microbots.environment.local_docker import image_builder


pytestmark = pytest.mark.unit


@pytest.fixture
def shell(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "ShellCommunicator", Path(image_builder.__file__).parent / "ShellCommunicator.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ShellCommunicator", module)
    # The module logs to /var/log/microbots, which only exists inside the container.
    with patch("logging.basicConfig"):
        spec.loader.exec_module(module)

    communicator = module.ShellCommunicator()
    assert communicator.start_session()
    yield communicator
    communicator.is_running = False
    if communicator.process and communicator.process.poll() is None:
        communicator.process.kill()


@pytest.fixture
def unstarted_shell(monkeypatch):
    """A ShellCommunicator instance that has never had start_session() called."""
    spec = importlib.util.spec_from_file_location(
        "ShellCommunicator", Path(image_builder.__file__).parent / "ShellCommunicator.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ShellCommunicator", module)
    with patch("logging.basicConfig"):
        spec.loader.exec_module(module)
    return module.ShellCommunicator()


def test_syntax_error_does_not_kill_the_shell(shell):
    result = shell.send_command("cat > /dev/null << 'EOF'\nbody\nEOF\n&& echo never", timeout=10)

    assert result.return_code != 0
    assert "syntax error" in result.stderr
    assert shell.send_command("echo alive", timeout=10).stdout == "alive"


def test_command_reading_stdin_gets_eof_instead_of_later_commands(shell):
    start = time.time()
    result = shell.send_command("sed -n '1,5p'", timeout=10)

    assert result.return_code == 0
    assert time.time() - start < 5
    assert shell.send_command("echo alive", timeout=10).stdout == "alive"


def test_directory_and_environment_persist_between_commands(shell, tmp_path):
    shell.send_command(f"cd {tmp_path} && export MICROBOTS_TEST=kept", timeout=10)

    assert shell.send_command("pwd", timeout=10).stdout == str(tmp_path)
    assert shell.send_command('echo "$MICROBOTS_TEST"', timeout=10).stdout == "kept"


def test_heredoc_with_special_characters_is_written_verbatim(shell, tmp_path):
    target = tmp_path / "out.txt"
    content = 'a ) ( $HOME `x` "q" \\n'

    shell.send_command(f"cat > {target} << 'EOF'\n{content}\nEOF", timeout=10)

    assert target.read_text() == content + "\n"


def test_exit_restarts_the_shell(shell):
    shell.send_command("exit 3", timeout=5)

    assert shell.send_command("echo alive", timeout=10).stdout == "alive"


def test_child_pids_skips_entries_it_cannot_read_or_parse(shell, monkeypatch):
    """_child_pids() must tolerate /proc entries that vanish mid-scan (OSError)
    or whose stat file is unparsable (IndexError/ValueError), instead of
    letting one bad entry blow up the whole scan."""
    real_listdir = os.listdir
    real_open = open

    def fake_listdir(path):
        if path == "/proc":
            # A pid that no longer exists (triggers OSError on open) and one
            # with a malformed stat file (triggers IndexError on parsing).
            return list(real_listdir(path)) + ["999999999", "888888888"]
        return real_listdir(path)

    def fake_open(path, *args, **kwargs):
        if path == "/proc/888888888/stat":
            return io.StringIO("malformed stat content with no parens")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "listdir", fake_listdir)
    monkeypatch.setattr("builtins.open", fake_open)

    # Should not raise despite the bogus entries, and should still report
    # whatever real children the shell actually has (none, here).
    assert shell._child_pids() == []


def test_child_pids_returns_empty_before_a_session_is_started(unstarted_shell):
    assert unstarted_shell._child_pids() == []


def test_async_command_is_sent_without_waiting(shell, tmp_path):
    marker_file = tmp_path / "ran"
    result = shell.send_command(f"touch {marker_file}", wait_for_output=False)

    assert result.return_code == 0
    assert result.stdout == "ASYNC: Not waiting for completion"

    # The command isn't awaited, but it still actually runs in the shell and
    # the shell stays usable afterwards.
    deadline = time.time() + 5
    while not marker_file.exists() and time.time() < deadline:
        time.sleep(0.1)
    assert marker_file.exists()
    assert shell.send_command("echo alive", timeout=10).stdout == "alive"


def test_send_command_reports_failure_when_restart_fails(shell, monkeypatch):
    shell.process.kill()
    shell.process.wait(timeout=5)
    monkeypatch.setattr(shell, "start_session", lambda: False)

    result = shell.send_command("echo hi", timeout=5)

    assert result.return_code == 1
    assert "could not be restarted" in result.stderr


def test_timed_out_command_is_killed_and_shell_recovers(shell):
    result = shell.send_command("sleep 30", timeout=1)

    assert result.return_code == 124
    start = time.time()
    assert shell.send_command("echo alive", timeout=10).stdout == "alive"
    assert time.time() - start < 5
