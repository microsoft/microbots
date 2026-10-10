"""Tests that the container shell survives the commands an agent may send it."""

import importlib.util
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


def test_timed_out_command_is_killed_and_shell_recovers(shell):
    result = shell.send_command("sleep 30", timeout=1)

    assert result.return_code == 124
    start = time.time()
    assert shell.send_command("echo alive", timeout=10).stdout == "alive"
    assert time.time() - start < 5
