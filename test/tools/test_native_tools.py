"""
Unit tests for the native tools: their YAML definitions and the file tools.

The file tools run against the host's bash, standing in for the sandbox shell,
so the shell commands they build are exercised for real.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from microbots.environment.Environment import CmdReturn, Environment
from microbots.tools.native_tools import OPENAI_NATIVE_TOOLS, RUN_COMMAND_TOOL, run_file_tool


class LocalShell(Environment):
    """Runs each command with the host's bash."""

    def start(self):
        pass

    def stop(self):
        pass

    def execute(self, command, timeout=300, sensitive=False):
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=timeout)
        return CmdReturn(stdout=result.stdout, stderr=result.stderr, return_code=result.returncode)


@pytest.fixture
def env():
    return LocalShell()


@pytest.mark.unit
class TestNativeToolDefinitions:

    def test_tools_are_loaded_from_yaml(self):
        assert RUN_COMMAND_TOOL.name == "run_command"
        assert [tool.name for tool in OPENAI_NATIVE_TOOLS] == ["run_command", "view_file", "create_file", "str_replace"]

    @pytest.mark.parametrize("tool", OPENAI_NATIVE_TOOLS, ids=lambda tool: tool.name)
    def test_schemas_meet_openai_strict_mode(self, tool):
        schema = tool.parameters
        assert schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])


@pytest.mark.unit
class TestViewFile:

    def test_numbers_every_line(self, env, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("first\nsecond\n")

        result = run_file_tool("view_file", {"path": str(path), "start_line": None, "end_line": None}, env)

        assert result.return_code == 0
        assert result.stdout == "     1\tfirst\n     2\tsecond"

    def test_shows_a_line_range(self, env, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("one\ntwo\nthree\nfour\n")

        result = run_file_tool("view_file", {"path": str(path), "start_line": 2, "end_line": 3}, env)

        assert result.stdout == "     2\ttwo\n     3\tthree"

    def test_missing_file_is_an_error(self, env, tmp_path):
        result = run_file_tool("view_file", {"path": str(tmp_path / "missing"), "start_line": None, "end_line": None}, env)

        assert result.return_code == 1
        assert "No such file" in result.stderr

    def test_binary_file_is_an_error(self, env, tmp_path):
        path = tmp_path / "image.bin"
        path.write_bytes(b"\xff\xfe\x00")

        result = run_file_tool("view_file", {"path": str(path), "start_line": None, "end_line": None}, env)

        assert result.return_code == 1
        assert "not a UTF-8 text file" in result.stderr


@pytest.mark.unit
class TestCreateFile:

    def test_writes_content_verbatim(self, env, tmp_path):
        path = tmp_path / "new" / "dir" / "script.sh"
        content = "echo \"$HOME\" 'quoted' `date` \\n\nEOF\n%s ünïcode\n"

        result = run_file_tool("create_file", {"path": str(path), "content": content}, env)

        assert result.return_code == 0
        assert path.read_text() == content

    def test_overwrites_an_existing_file(self, env, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("old")

        run_file_tool("create_file", {"path": str(path), "content": "new"}, env)

        assert path.read_text() == "new"

    def test_creates_an_empty_file(self, env, tmp_path):
        path = tmp_path / "empty.txt"

        result = run_file_tool("create_file", {"path": str(path), "content": ""}, env)

        assert result.return_code == 0
        assert path.read_text() == ""

    def test_unwritable_path_is_an_error(self, env, tmp_path):
        not_a_directory = tmp_path / "a.txt"
        not_a_directory.write_text("keep")

        result = run_file_tool("create_file", {"path": str(not_a_directory / "b.txt"), "content": "x"}, env)

        assert result.return_code == 1
        assert str(not_a_directory) in result.stderr
        assert not_a_directory.read_text() == "keep"


@pytest.mark.unit
class TestStrReplace:

    def test_replaces_the_unique_occurrence(self, env, tmp_path):
        path = tmp_path / "a.py"
        path.write_text("def f():\n    return 1\n")

        result = run_file_tool(
            "str_replace", {"path": str(path), "old_str": "return 1", "new_str": "return '$2'"}, env
        )

        assert result.return_code == 0
        assert path.read_text() == "def f():\n    return '$2'\n"

    def test_rejects_text_that_is_missing(self, env, tmp_path):
        path = tmp_path / "a.py"
        path.write_text("x = 1\n")

        result = run_file_tool("str_replace", {"path": str(path), "old_str": "y = 1", "new_str": "y = 2"}, env)

        assert result.return_code == 1
        assert "appears 0 times" in result.stderr
        assert path.read_text() == "x = 1\n"

    def test_rejects_text_that_appears_more_than_once(self, env, tmp_path):
        path = tmp_path / "a.py"
        path.write_text("x = 1\nx = 1\n")

        result = run_file_tool("str_replace", {"path": str(path), "old_str": "x = 1", "new_str": "x = 2"}, env)

        assert result.return_code == 1
        assert "appears 2 times" in result.stderr
        assert path.read_text() == "x = 1\nx = 1\n"


@pytest.mark.unit
def test_unknown_tool_is_an_error(env):
    result = run_file_tool("delete_everything", {}, env)

    assert result.return_code == 1
    assert "Unknown tool" in result.stderr
