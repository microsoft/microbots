import json
from unittest.mock import Mock, patch

import pytest

from microbots import MicroBot, BotRunResult
from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.extras.mount import Mount
from microbots.tools.tool_definitions.memory_tool import MemoryTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(task_done, thoughts, command=""):
    """Build a mock Anthropic API response; unless done, it calls the run_command tool with ``command``."""
    text_block = Mock()
    text_block.type = "text"
    text_block.text = thoughts

    resp = Mock()
    resp.content = [text_block]
    if not task_done:
        tool_use_block = Mock()
        tool_use_block.type = "tool_use"
        tool_use_block.id = "toolu_1"
        tool_use_block.name = "run_command"
        tool_use_block.input = {"command": command}
        resp.content.append(tool_use_block)
    return resp


def _make_openai_response(task_done, thoughts, command=""):
    """Build a mock OpenAI API response with output_text."""
    resp = Mock()
    resp.output_text = json.dumps({
        "task_done": task_done,
        "thoughts": thoughts,
        "command": command,
    })
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryToolWiring:
    """Unit tests for MemoryTool dispatch with a mocked Anthropic client."""

    @pytest.fixture()
    def memory_dir(self, tmp_path):
        d = tmp_path / "memory"
        d.mkdir()
        return d

    @pytest.fixture()
    def bot(self, memory_dir):
        """Create a MicroBot with a mocked Anthropic provider and a MemoryTool.

        The LLM client is mocked, but the rest of the stack is real:
        tool dispatch and memory file operations.
        """
        tool = MemoryTool(
            memory_dir=str(memory_dir),
            usage_instructions_to_llm="Use the memory tool to persist notes.",
        )

        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        anthropic_deployment = "claude-sonnet-4-5"

        with patch("microbots.llm.anthropic_api.Anthropic") as mock_anthropic_cls, \
             patch("microbots.llm.anthropic_api.api_key", "test-key"), \
             patch("microbots.llm.anthropic_api.endpoint", "https://api.anthropic.com"), \
             patch("microbots.llm.anthropic_api.deployment_name", anthropic_deployment):

            bot = MicroBot(
                model=f"anthropic/{anthropic_deployment}",
                system_prompt="You are a helpful assistant.",
                additional_tools=[tool],
                environment=mock_env,
            )

            self._mock_client = mock_anthropic_cls.return_value
            yield bot
            del bot

    # -- Upgrade verification -----------------------------------------------

    def test_memory_tool_is_retained(self, bot):
        """MemoryTool passed to MicroBot should remain provider-agnostic."""
        memory_tools = [t for t in bot.additional_tools if isinstance(t, MemoryTool)]
        assert len(memory_tools) == 1, "Expected exactly one MemoryTool to remain attached"

    # -- Create file via text command ---------------------------------------

    def test_create_memory_file_via_tool_dispatch(self, bot, memory_dir):
        """LLM requests a memory create → MicroBot dispatches → file appears on disk."""
        # Sequence:
        # 1. ask(task) → API returns JSON command (memory create)
        # 2. ask(command output) → API returns end_turn (task_done=True)
        self._mock_client.messages.create.side_effect = [
            _make_anthropic_response(
                task_done=False,
                thoughts="I'll save a note to memory.",
                command='memory create /memories/notes.md "Hello from integration test"',
            ),
            _make_anthropic_response(
                task_done=True,
                thoughts="Saved a note to memory successfully.",
            ),
        ]

        result: BotRunResult = bot.run(
            "Save a note saying 'Hello from integration test'",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True
        assert result.error is None

        # Verify the file was actually created on disk
        # _resolve("/memories/notes.md") strips the "memories/" prefix → memory_dir/notes.md
        created_file = memory_dir / "notes.md"
        assert created_file.exists(), f"Expected {created_file} to be created"
        assert created_file.read_text() == "Hello from integration test"

    # -- View file via text command -----------------------------------------

    def test_view_memory_file_via_tool_dispatch(self, bot, memory_dir):
        """LLM requests a memory view → MicroBot dispatches → file content returned."""
        # Pre-create a file in memory
        # _resolve("/memories/existing.md") → memory_dir/existing.md
        (memory_dir / "existing.md").write_text("Previously saved content")

        self._mock_client.messages.create.side_effect = [
            _make_anthropic_response(
                task_done=False,
                thoughts="Let me check my memory.",
                command="memory view /memories/existing.md",
            ),
            _make_anthropic_response(
                task_done=True,
                thoughts="Found previously saved content in memory.",
            ),
        ]

        result: BotRunResult = bot.run(
            "Check your memory for existing notes",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True

        # The view output is sent back to the API as the result of the tool call
        assert self._mock_client.messages.create.call_count == 2
        tool_result = bot.llm.messages[2]["content"][0]
        assert tool_result["type"] == "tool_result"
        assert "Previously saved content" in tool_result["content"]

    # -- Multiple tool calls in sequence ------------------------------------

    def test_create_then_view_memory_file(self, bot, memory_dir):
        """LLM creates a file, then views it — both dispatched via MicroBot loop."""
        self._mock_client.messages.create.side_effect = [
            # Step 1: create file
            _make_anthropic_response(
                task_done=False,
                thoughts="Creating a todo list.",
                command='memory create /memories/todo.md "- Fix bug #42\n- Write tests"',
            ),
            # Step 2: view file
            _make_anthropic_response(
                task_done=False,
                thoughts="Let me verify what I wrote.",
                command="memory view /memories/todo.md",
            ),
            # Step 3: done
            _make_anthropic_response(
                task_done=True,
                thoughts="Created and verified the todo list.",
            ),
        ]

        result: BotRunResult = bot.run(
            "Create a todo list and verify it was saved",
            max_iterations=10,
            timeout_in_seconds=30,
        )

        assert result.status is True
        assert result.error is None

        # File should exist with correct content
        created_file = memory_dir / "todo.md"
        assert created_file.exists()
        assert "Fix bug #42" in created_file.read_text()

    # -- Non-memory commands still go to environment ------------------------

    def test_non_memory_commands_go_to_environment(self, bot):
        """Regular shell commands should be dispatched to the environment, not the memory tool."""
        self._mock_client.messages.create.side_effect = [
            _make_anthropic_response(
                task_done=False,
                thoughts="Let me check the files.",
                command="ls -la",
            ),
            _make_anthropic_response(
                task_done=True,
                thoughts="Done.",
            ),
        ]

        result: BotRunResult = bot.run(
            "List the files",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True
        # The environment.execute should have been called with "ls -la"
        bot.environment.execute.assert_called_with("ls -la")


# ---------------------------------------------------------------------------
# OpenAI wiring tests (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryToolWiringOpenAI:
    """Unit tests for MemoryTool dispatch with a mocked OpenAI client."""

    @pytest.fixture()
    def memory_dir(self, tmp_path):
        d = tmp_path / "memory"
        d.mkdir()
        return d

    @pytest.fixture()
    def bot(self, memory_dir):
        tool = MemoryTool(
            memory_dir=str(memory_dir),
            usage_instructions_to_llm="Use the memory tool to persist notes.",
        )

        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        openai_deployment = "gpt-4"

        with patch("microbots.llm.azure_openai_api.AzureOpenAI") as mock_openai_cls, \
             patch("microbots.llm.azure_openai_api.api_key", "test-key"), \
             patch("microbots.llm.azure_openai_api.endpoint", "https://test-resource.openai.azure.com"), \
             patch("microbots.llm.azure_openai_api.deployment_name", openai_deployment):

            bot = MicroBot(
                model=f"azure-openai/{openai_deployment}",
                system_prompt="You are a helpful assistant.",
                additional_tools=[tool],
                environment=mock_env,
            )

            self._mock_client = mock_openai_cls.return_value
            yield bot
            del bot

    def test_memory_tool_is_retained(self, bot):
        memory_tools = [t for t in bot.additional_tools if isinstance(t, MemoryTool)]
        assert len(memory_tools) == 1

    def test_create_memory_file_via_tool_dispatch(self, bot, memory_dir):
        """LLM requests a memory create → MicroBot dispatches → file appears on disk."""
        self._mock_client.responses.create.side_effect = [
            _make_openai_response(
                task_done=False,
                thoughts="I'll save a note to memory.",
                command='memory create /memories/notes.md "Hello from OpenAI test"',
            ),
            _make_openai_response(
                task_done=True,
                thoughts="Saved a note to memory successfully.",
            ),
        ]

        result: BotRunResult = bot.run(
            "Save a note saying 'Hello from OpenAI test'",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True
        assert result.error is None

        created_file = memory_dir / "notes.md"
        assert created_file.exists()
        assert created_file.read_text() == "Hello from OpenAI test"

    def test_view_memory_file_via_tool_dispatch(self, bot, memory_dir):
        """LLM requests a memory view → MicroBot dispatches → file content returned."""
        (memory_dir / "existing.md").write_text("Previously saved content")

        self._mock_client.responses.create.side_effect = [
            _make_openai_response(
                task_done=False,
                thoughts="Let me check my memory.",
                command="memory view /memories/existing.md",
            ),
            _make_openai_response(
                task_done=True,
                thoughts="Found previously saved content in memory.",
            ),
        ]

        result: BotRunResult = bot.run(
            "Check your memory for existing notes",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True

    def test_non_memory_commands_go_to_environment(self, bot):
        """Regular shell commands should be dispatched to the environment."""
        self._mock_client.responses.create.side_effect = [
            _make_openai_response(
                task_done=False,
                thoughts="Let me check the files.",
                command="ls -la",
            ),
            _make_openai_response(
                task_done=True,
                thoughts="Done.",
            ),
        ]

        result: BotRunResult = bot.run(
            "List the files",
            max_iterations=5,
            timeout_in_seconds=30,
        )

        assert result.status is True
        bot.environment.execute.assert_called_with("ls -la")


# ---------------------------------------------------------------------------
# Real integration tests — require Azure OpenAI or OpenAI + Docker
# ---------------------------------------------------------------------------

from microbots.MicroBot import system_prompt_common_for

def _memory_system_prompt(sandbox_path, model):
    return f"""{system_prompt_common_for(model)}
The project code is available at {sandbox_path} in your shell environment.
"""


def _create_test_project(base_dir):
    """Create a small Python project with deliberate code issues.

    Returns the path to the project directory.
    """
    project = base_dir / "myproject"
    project.mkdir()

    # utils.py — unused import 'os'
    (project / "utils.py").write_text(
        "import os\n"
        "import json\n"
        "\n"
        "\n"
        "def parse_config(raw: str) -> dict:\n"
        '    """Parse a JSON config string."""\n'
        "    return json.loads(raw)\n"
    )

    # handler.py — missing null check around line 42
    lines = [f"# handler.py — request handler\n"]
    lines += [f"# line {i}\n" for i in range(2, 42)]
    lines.append("def handle_request(request):\n")  # line 42
    lines.append("    user = request.get('user')\n")  # line 43
    lines.append("    return user.name\n")  # line 44 — will crash if user is None
    (project / "handler.py").write_text("".join(lines))

    # client.py — deprecated API call around line 88
    lines = [f"# client.py — HTTP client wrapper\n"]
    lines += [f"# line {i}\n" for i in range(2, 88)]
    lines.append("import urllib.request\n")  # line 88
    lines.append("def fetch(url):\n")  # line 89
    lines.append("    return urllib.request.urlopen(url).read()  # deprecated: use requests\n")
    (project / "client.py").write_text("".join(lines))

    return project


@pytest.mark.integration
@pytest.mark.slow
class TestMemoryToolRealIntegration:
    """End-to-end integration tests with Azure OpenAI and OpenAI.

    These tests exercise the full MicroBot → LLM → memory tool pipeline
    with no mocking.  A small Python project with deliberate code issues
    is mounted into the Docker sandbox so the bot has real files to work on.

    Run with::

        pytest -m integration test/bot/test_memory_tool_integration.py -v

    Requires ``AZURE_OPENAI_DEPLOYMENT_NAME`` (or defaults to
    ``mini-swe-agent-gpt5``) and valid Azure OpenAI credentials. The
    OpenAI run uses ``OPENAI_MODEL`` (or ``gpt-5``) and is skipped
    without ``OPENAI_API_KEY``.
    """

    @pytest.fixture()
    def memory_dir(self, tmp_path):
        d = tmp_path / "memory"
        d.mkdir()
        return d

    @pytest.fixture()
    def test_project(self, tmp_path):
        return _create_test_project(tmp_path)

    @pytest.fixture()
    def memory_bot(self, memory_dir, test_project, openai_model):
        tool = MemoryTool(
            memory_dir=str(memory_dir),
        )

        sandbox_path = f"{DOCKER_WORKING_DIR}/{test_project.name}"
        folder_mount = Mount(
            str(test_project),
            sandbox_path,
            PermissionLabels.READ_ONLY,
        )

        bot = MicroBot(
            model=openai_model,
            system_prompt=_memory_system_prompt(sandbox_path, openai_model),
            additional_tools=[tool],
            folder_to_mount=folder_mount,
        )

        yield bot
        del bot

    def test_create_memory_file(self, memory_bot, memory_dir):
        """MicroBot should use memory tool while reviewing code for issues."""
        result: BotRunResult = memory_bot.run(
            task=(
                "Review the Python project for code quality issues. "
                "Check each .py file for unused imports, missing error handling, "
                "and deprecated API usage. Report all issues you find."
            ),
            max_iterations=15,
            timeout_in_seconds=300,
        )

        assert result.status is True, f"Task failed: {result.error}"
        assert result.error is None

        saved_files = [f for f in memory_dir.rglob("*") if f.is_file()]
        assert len(saved_files) >= 1, (
            f"Expected at least one file created in memory. "
            f"Found: {saved_files}"
        )
