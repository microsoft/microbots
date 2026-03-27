"""
This test uses the Microbot base class to create a custom bot and tries to solve
https://github.com/SWE-agent/test-repo/issues/1.
This test will create multiple custom bots - a reading bot, a writing bot using the base class.
"""

import json
import os
from pathlib import Path
from pprint import pformat
import subprocess
import sys
from unittest.mock import patch, Mock

import pytest
# Add src directory to path to import from local source
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from microbots import MicroBot, BotRunResult
from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.extras.mount import Mount, MountType
from microbots.environment.Environment import CmdReturn
from microbots.llm.llm import llm_output_format_str, LLMAskResponse
from microbots.tools.internal_tool import Tool


SYSTEM_PROMPT = f"""
You are a helpful python programmer who is good in debugging code.
You have the python repo where you're working mounted at {DOCKER_WORKING_DIR}.
You have a shell session open for you.
I will provide a task to achieve using only the shell commands.
You cannot run any interactive commands like vim, nano, etc. To update a file, you must use `sed` or `echo` commands.
Do not run recursive `find`, `tree`, or `sed` across the whole repo (especially `.git`). Inspect only directories/files directly related to the failure.
When running pytest, ONLY test the specific file mentioned in the task - do not run the entire test directory or test suite.
You will provide the commands to achieve the task in this particular below json format, Ensure all the time to respond in this format only and nothing else, also all the properties ( task_done, command, result ) are mandatory on each response

You must send `task_done` as true only when you have completed the task. It means all the commands you wanted to run are completed in the previous steps. You should not run any more commands while you're sending `task_done` as true.
{llm_output_format_str}
"""


@pytest.fixture(scope="function")
def no_mount_microBot():
    local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')
    bot = MicroBot(
        model=f"ollama-local/{local_model}",
        system_prompt=SYSTEM_PROMPT,
    )
    yield bot
    del bot

@pytest.mark.integration
@pytest.mark.docker
class TestMicrobotIntegration:

    @pytest.fixture(scope="function")
    def log_file_path(self, tmpdir: Path):
        assert tmpdir.exists()
        yield tmpdir / "error.log"
        if tmpdir.exists():
            subprocess.run(["sudo", "rm", "-rf", str(tmpdir)])

    @pytest.fixture(scope="function")
    def ro_mount(self, test_repo: Path):
        assert test_repo is not None
        return Mount(
            str(test_repo), f"{DOCKER_WORKING_DIR}/{test_repo.name}", PermissionLabels.READ_ONLY
        )

    @pytest.fixture(scope="function")
    def ro_microBot(self, ro_mount: Mount):
        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')
        bot = MicroBot(
            model=f"ollama-local/{local_model}",
            system_prompt=SYSTEM_PROMPT,
            folder_to_mount=ro_mount,
        )
        yield bot
        del bot


    @pytest.fixture(scope="function")
    def anthropic_microBot(self):
        anthropic_deployment = os.getenv('ANTHROPIC_DEPLOYMENT_NAME', 'claude-sonnet-4-5')
        with patch('microbots.llm.anthropic_api.endpoint', 'https://api.anthropic.com'), \
             patch('microbots.llm.anthropic_api.deployment_name', anthropic_deployment), \
             patch('microbots.llm.anthropic_api.api_key', 'test-api-key'), \
             patch('microbots.llm.anthropic_api.Anthropic'):
            bot = MicroBot(
                model=f"anthropic/{anthropic_deployment}",
                system_prompt=SYSTEM_PROMPT,
            )
            yield bot
            del bot

    @pytest.mark.ollama_local
    def test_microbot_ro_mount(self, ro_microBot, test_repo: Path):
        logger.debug(f"Testing MicroBot with read-only mount. Mounted repo path: {test_repo}")
        assert test_repo is not None
        assert os.path.exists(test_repo)

        result: CmdReturn = ro_microBot.environment.execute(f"cd {DOCKER_WORKING_DIR}/{test_repo.name} && ls -la", timeout=60)
        logger.info(f"Command Execution Result: \nstdout={result.stdout}, \nstderr={result.stderr}, \nreturn_code={result.return_code}")
        assert result.return_code == 0
        assert "tests" in result.stdout

        result = ro_microBot.environment.execute("cd tests; ls -la", timeout=60)
        logger.info(f"Command Execution Result: \nstdout={result.stdout}, \nstderr={result.stderr}, \nreturn_code={result.return_code}")
        assert result.return_code == 0
        assert "missing_colon.py" in result.stdout

    @pytest.mark.ollama_local
    def test_microbot_overlay_teardown(self, ro_microBot, caplog):
        caplog.clear()
        caplog.set_level(logging.INFO)

        del ro_microBot

        assert "Failed to remove working directory" not in caplog.text

    def test_microbot_anthropic_initialization(self, anthropic_microBot):
        """Test that MicroBot correctly initializes with Anthropic model provider."""
        assert anthropic_microBot is not None
        assert anthropic_microBot.model_provider == "anthropic"
        assert anthropic_microBot.llm is not None
        from microbots.llm.anthropic_api import AnthropicApi
        assert isinstance(anthropic_microBot.llm, AnthropicApi)

    @pytest.mark.slow
    def test_microbot_2bot_combo(self, log_file_path, test_repo, issue_1):
        assert test_repo is not None
        assert log_file_path is not None

        verify_function = issue_1[1]

        test_repo_mount_ro = Mount(
            str(test_repo),
            f"{DOCKER_WORKING_DIR}/{test_repo.name}",
            PermissionLabels.READ_ONLY
        )
        model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"
        testing_bot = MicroBot(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            folder_to_mount=test_repo_mount_ro,
        )

        response: BotRunResult = testing_bot.run(
            "Execute tests/missing_colon.py and provide the error message. Your response should be in 'thoughts' field.",
            timeout_in_seconds=300
        )

        logger.debug(f"Custom Reading Bot - Status: {response.status}, Result: {response.result}, Error: {response.error}")

        assert response.status
        assert response.result is not None
        assert response.error is None

        with open(log_file_path, "w") as log_file:
            log_file.write(response.result)

        test_repo_mount_rw = Mount(
            str(test_repo), f"{DOCKER_WORKING_DIR}/{test_repo.name}", PermissionLabels.READ_WRITE
        )
        model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"
        coding_bot = MicroBot(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            folder_to_mount=test_repo_mount_rw,
        )

        additional_mounts = Mount(
            str(log_file_path),
            "/var/log/",
            PermissionLabels.READ_ONLY,
            MountType.COPY,
        )
        response: BotRunResult = coding_bot.run(
            f"The test file tests/missing_colon.py is failing. Please fix the code. The error log is available at /var/log/{log_file_path.basename}.",
            additional_mounts=[additional_mounts],
            timeout_in_seconds=300
        )

        print(f"Custom Coding Bot - Status: {response.status}, Result: {response.result}, Error: {response.error}")

        assert response.status
        assert response.error is None

        verify_function(test_repo)

    def test_microbot_anthropic_with_mount(self, test_repo):
        """Test that MicroBot with Anthropic provider works with mounted folders."""
        assert test_repo is not None

        test_repo_mount_ro = Mount(
            str(test_repo), f"{DOCKER_WORKING_DIR}/{test_repo.name}", PermissionLabels.READ_ONLY
        )
        anthropic_deployment = os.getenv('ANTHROPIC_DEPLOYMENT_NAME', 'claude-sonnet-4-5')
        with patch('microbots.llm.anthropic_api.endpoint', 'https://api.anthropic.com'), \
             patch('microbots.llm.anthropic_api.deployment_name', anthropic_deployment), \
             patch('microbots.llm.anthropic_api.api_key', 'test-api-key'), \
             patch('microbots.llm.anthropic_api.Anthropic'):
            bot = MicroBot(
                model=f"anthropic/{anthropic_deployment}",
                system_prompt=SYSTEM_PROMPT,
                folder_to_mount=test_repo_mount_ro,
            )
            assert bot is not None
            assert bot.model_provider == "anthropic"
            from microbots.llm.anthropic_api import AnthropicApi
            assert isinstance(bot.llm, AnthropicApi)
            del bot


@pytest.mark.unit
class TestMicrobotUnit:
    """Unit tests for MicroBot command safety validation."""

    def test_incorrect_code_mount_type(self):
        """Test that ValueError is raised when folder_to_mount uses COPY mount type."""
        invalid_mount = Mount(
            "/dummy/path",
            f"{DOCKER_WORKING_DIR}/test",
            PermissionLabels.READ_ONLY,
            MountType.COPY,  # COPY is not supported for folder_to_mount
        )

        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')
        with pytest.raises(ValueError, match="Only MOUNT mount type is supported for folder_to_mount"):
            MicroBot(
                model=f"ollama-local/{local_model}",
                system_prompt=SYSTEM_PROMPT,
                folder_to_mount=invalid_mount,
            )

    @pytest.mark.ollama_local
    def test_incorrect_copy_mount_type(self, no_mount_microBot):
        """Test that ValueError is raised when additional_mounts uses MOUNT mount type."""
        invalid_additional_mount = Mount(
            "/dummy/log/file.txt",
            "/var/log/file.txt",
            PermissionLabels.READ_ONLY,
            MountType.MOUNT,  # MOUNT is not supported for additional_mounts
        )

        with pytest.raises(ValueError, match="Only COPY mount type is supported for additional mounts for now"):
            no_mount_microBot.run(
                "Test task",
                additional_mounts=[invalid_additional_mount],
                timeout_in_seconds=60
            )

    def test_incorrect_model_provider(self):
        """Test that ValueError is raised for unsupported model providers."""
        with pytest.raises(ValueError, match="Unsupported model provider: unsupported-provider"):
            MicroBot(
                model="unsupported-provider/some-model",
                system_prompt=SYSTEM_PROMPT,
            )

    def test_incorrect_model_format(self):
        """Test that ValueError is raised for incorrectly formatted model strings."""
        with pytest.raises(ValueError, match="Model should be in the format <provider>/<model_name>"):
            MicroBot(
                model="invalidmodelname",
                system_prompt=SYSTEM_PROMPT,
            )

    @pytest.mark.ollama_local
    def test_invalid_max_iterations(self, no_mount_microBot):
        """Test that ValueError is raised for invalid max_iterations values"""
        assert no_mount_microBot is not None

        # Test with max_iterations = 0
        with pytest.raises(ValueError) as exc_info:
            no_mount_microBot.run(
                "This is a test task.",
                max_iterations=0
            )
        assert "max_iterations must be greater than 0" in str(exc_info.value)

        # Test with max_iterations = -1
        with pytest.raises(ValueError) as exc_info:
            no_mount_microBot.run(
                "This is a test task.",
                max_iterations=-1
            )
        assert "max_iterations must be greater than 0" in str(exc_info.value)

        # Test with max_iterations = -10
        with pytest.raises(ValueError) as exc_info:
            no_mount_microBot.run(
                "This is a test task.",
                max_iterations=-10
            )
        assert "max_iterations must be greater than 0" in str(exc_info.value)

    @pytest.mark.ollama_local
    def test_max_iterations_exceeded(self, no_mount_microBot, monkeypatch):
        assert no_mount_microBot is not None

        def mock_ask(message: str):
            return LLMAskResponse(command="echo 'Hello World'", task_done=False, thoughts="")

        monkeypatch.setattr(no_mount_microBot.llm, "ask", mock_ask)

        response: BotRunResult = no_mount_microBot.run(
            "This is a test to check max iterations handling.",
            timeout_in_seconds=120,
            max_iterations=3
        )

        print(f"Max Iterations Test - Status: {response.status}, Result: {response.result}, Error: {response.error}")

        assert not response.status
        assert response.error == "Max iterations 3 reached"

    @pytest.mark.ollama_local
    def test_timeout_handling(self, no_mount_microBot, monkeypatch):
        assert no_mount_microBot is not None

        def mock_ask(message: str):
            return LLMAskResponse(command="sleep 10", task_done=False, thoughts="")

        monkeypatch.setattr(no_mount_microBot.llm, "ask", mock_ask)

        response: BotRunResult = no_mount_microBot.run(
            "This is a test to check timeout handling.",
            timeout_in_seconds=5,
            max_iterations=10
        )

        print(f"Timeout Handling Test - Status: {response.status}, Result: {response.result}, Error: {response.error}")

        assert not response.status
        assert response.error == "Timeout of 5 seconds reached"

    @pytest.mark.ollama_local
    def test_dangerous_command_blocking(self, no_mount_microBot, monkeypatch, caplog):
        """Test that dangerous commands are blocked and LLM receives detailed explanation."""
        caplog.set_level(logging.INFO)

        call_count = [0]

        def mock_ask(message: str):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call returns dangerous command
                return LLMAskResponse(command="ls -R /path", task_done=False, thoughts="")
            else:
                # After receiving error with explanation, return safe command
                assert "COMMAND_ERROR:" in message
                assert "Dangerous command detected and blocked" in message
                assert "REASON:" in message
                assert "ALTERNATIVE:" in message
                return LLMAskResponse(command="pwd", task_done=True, thoughts="")

        monkeypatch.setattr(no_mount_microBot.llm, "ask", mock_ask)

        response: BotRunResult = no_mount_microBot.run(
            "List files",
            timeout_in_seconds=60,
            max_iterations=10
        )

        # Verify dangerous command was logged with explanation
        assert "Dangerous command detected and blocked: ls -R /path" in caplog.text
        assert "REASON:" in caplog.text
        assert "ALTERNATIVE:" in caplog.text

        # Verify task completed after providing safe command
        assert response.status

    @pytest.mark.parametrize("command,expected_safe", [
        # Dangerous: Recursive ls commands
        ("ls -R", False),
        ("ls -lR", False),
        ("ls -alR", False),
        ("ls -Rl", False),
        ("ls -r /path", False),
        ("ls -laR /some/path", False),
        ("ls -Ra", False),
        # Dangerous: Tree commands
        ("tree", False),
        ("tree /path", False),
        ("tree -L 3", False),
        # Dangerous: Recursive rm commands
        ("rm -r /path", False),
        ("rm -rf /path", False),
        ("rm -fr /path", False),
        ("rm -Rf /path", False),
        ("rm --recursive /path", False),
        ("rm -rf .", False),
        # Dangerous: Find without maxdepth
        ("find /path -name '*.py'", False),
        ("find . -type f", False),
        ("find /home -name 'test*'", False),
        # Safe: Find with maxdepth
        ("find /path -name '*.py' -maxdepth 2", True),
        ("find . -type f -maxdepth 1", True),
        ("find /home -maxdepth 3 -name 'test*'", True),
        # Safe: Common commands (including the key test case)
        ("ls -la", True),
        ("ls -la /workdir/test-repo && ls -la /workdir/test-repo/tests", True),
        ("ls -lt", True),
        ("ls -al", True),
        ("ls /path/to/dir", True),
        ("rm file.txt", True),
        ("rm -f file.txt", True),
        ("cat file.txt", True),
        ("grep 'pattern' file.txt", True),
        ("echo 'hello'", True),
        ("cd /path", True),
        ("pwd", True),
        ("python script.py", True),
        ("git status", True),
        # Invalid inputs
        (None, False),
        ("", False),
        ("   ", False),
        (123, False),
        ([], False),
        ({}, False),
    ])
    def test_is_safe_command(self, command, expected_safe):
        """Test command safety validation for all scenarios."""
        # Create a minimal bot instance without environment (no container)
        bot = MicroBot.__new__(MicroBot)  # Create instance without calling __init__
        is_safe, explanation = bot._is_safe_command(command)
        assert is_safe == expected_safe, f"Command '{command}' expected safe={expected_safe}, got {is_safe}"

        # Verify explanation is provided when command is not safe
        if not expected_safe:
            assert explanation is not None, f"Expected explanation for unsafe command '{command}'"
            assert "REASON:" in explanation
            assert "ALTERNATIVE:" in explanation

    @pytest.mark.parametrize("command,should_be_dangerous,expected_keyword", [
        # Dangerous commands
        ("ls -R", True, "Recursive ls"),
        ("ls -lR /path", True, "Recursive ls"),
        ("tree", True, "Tree command"),
        ("rm -rf /path", True, "Recursive rm"),
        ("find . -name '*.py'", True, "Find command without -maxdepth"),
        # Safe commands
        ("ls -la", False, None),
        ("ls -la /workdir/test-repo && ls -la /workdir/test-repo/tests", False, None),
        ("rm file.txt", False, None),
        ("find /path -maxdepth 2 -name '*.py'", False, None),
    ])
    def test_get_dangerous_command_explanation(self, command, should_be_dangerous, expected_keyword):
        """Test that dangerous commands return explanations with REASON and ALTERNATIVE."""
        bot = MicroBot.__new__(MicroBot)
        result = bot._get_dangerous_command_explanation(command)

        if should_be_dangerous:
            assert result is not None, f"Command '{command}' should have explanation"
            assert "REASON:" in result and "ALTERNATIVE:" in result
            assert expected_keyword in result
        else:
            assert result is None, f"Command '{command}' should be safe"

    def test_dangerous_command_explanation_format(self):
        """Test that dangerous command explanations have correct format with reason and alternative."""
        bot = MicroBot.__new__(MicroBot)
        explanation = bot._get_dangerous_command_explanation("ls -R")

        assert explanation is not None
        lines = explanation.split('\n')
        assert len(lines) >= 2
        assert lines[0].startswith("REASON:")
        assert lines[1].startswith("ALTERNATIVE:")
        assert len(lines[0].replace("REASON:", "").strip()) > 0
        assert len(lines[1].replace("ALTERNATIVE:", "").strip()) > 0



    def test_tool_usage_instructions_appended_to_system_prompt(self):
        """Test that tool usage instructions are appended to the system prompt when creating LLM."""

        # Create a mock tool with usage instructions
        mock_tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters=None,
            usage_instructions_to_llm="# Test Tool Usage\nUse this tool for testing purposes only.",
            install_commands=["echo 'test'"],
            env_variables=[],
            files_to_copy=[],
        )

        base_system_prompt = "You are a helpful assistant."

        # Create a mock environment
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        # Mock the environment and LLM creation to avoid actual Docker/API calls
        with patch('microbots.llm.openai_api.OpenAI'):
            # Create a MicroBot with the mock tool
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt=base_system_prompt,
                additional_tools=[mock_tool],
                environment=mock_env,
            )

            # Verify that the LLM was created with the combined system prompt
            # The system prompt should include both the base prompt and the tool usage instructions
            from microbots.llm.openai_api import OpenAIApi
            assert isinstance(bot.llm, OpenAIApi)
            assert base_system_prompt in bot.llm.system_prompt
            assert "# Test Tool Usage" in bot.llm.system_prompt
            assert "Use this tool for testing purposes only." in bot.llm.system_prompt

    def test_multiple_tool_usage_instructions_appended(self):
        """Test that multiple tool usage instructions are all appended to the system prompt."""

        # Create multiple mock tools with usage instructions
        tool1 = Tool(
            name="tool1",
            description="First tool",
            parameters=None,
            usage_instructions_to_llm="# Tool 1 Usage\nInstructions for tool 1.",
            install_commands=["echo 'tool1'"],
            env_variables=[],
            files_to_copy=[],
        )

        tool2 = Tool(
            name="tool2",
            description="Second tool",
            parameters=None,
            usage_instructions_to_llm="# Tool 2 Usage\nInstructions for tool 2.",
            install_commands=["echo 'tool2'"],
            env_variables=[],
            files_to_copy=[],
        )

        base_system_prompt = "You are a helpful assistant."

        # Create a mock environment
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        # Mock the environment and LLM creation
        with patch('microbots.llm.anthropic_api.Anthropic'):
            bot = MicroBot(
                model="anthropic/claude-sonnet-4-5",
                system_prompt=base_system_prompt,
                additional_tools=[tool1, tool2],
                environment=mock_env,
            )

            # Verify both tool instructions are in the system prompt
            from microbots.llm.anthropic_api import AnthropicApi
            assert isinstance(bot.llm, AnthropicApi)
            assert base_system_prompt in bot.llm.system_prompt
            assert "# Tool 1 Usage" in bot.llm.system_prompt
            assert "Instructions for tool 1." in bot.llm.system_prompt
            assert "# Tool 2 Usage" in bot.llm.system_prompt
            assert "Instructions for tool 2." in bot.llm.system_prompt

    def test_no_tool_usage_instructions_when_no_tools(self):
        """Test that system prompt remains unchanged when no tools are provided."""
        base_system_prompt = "You are a helpful assistant."

        # Create a mock environment
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        # Mock the environment and LLM creation
        with patch.dict('os.environ', {'LOCAL_MODEL_NAME': 'test-model', 'LOCAL_MODEL_PORT': '11434'}), \
             patch('microbots.llm.ollama_local.requests'):

            bot = MicroBot(
                model="ollama-local/test-model",
                system_prompt=base_system_prompt,
                additional_tools=[],
                environment=mock_env,
            )

            # Verify the system prompt is unchanged
            from microbots.llm.ollama_local import OllamaLocal
            assert isinstance(bot.llm, OllamaLocal)
            assert bot.llm.system_prompt == base_system_prompt

    def test_run_json_output_with_content_key(self):
        """Test anthropic-text-editor hack: JSON output with 'content' key is reformatted using pformat."""
        json_content = {"content": ["line 1", "line 2"], "other_key": "data"}
        mock_env = Mock()
        mock_env.execute.return_value = Mock(
            return_code=0, stdout=json.dumps(json_content), stderr=""
        )

        with patch('microbots.llm.openai_api.OpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test prompt",
                environment=mock_env,
            )

        call_count = [0]
        captured_output = [None]

        def mock_ask(message: str):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMAskResponse(command="echo test", task_done=False, thoughts="running")
            else:
                captured_output[0] = message
                return LLMAskResponse(command="", task_done=True, thoughts="done")

        bot.llm.ask = mock_ask

        result = bot.run("test task", max_iterations=5, timeout_in_seconds=60)

        assert result.status is True
        # The output passed to LLM should be pformat of the "content" value
        assert captured_output[0] == pformat(json_content["content"])

    def test_run_json_output_without_content_key(self):
        """Test anthropic-text-editor hack: JSON output without 'content' key preserves raw stdout."""
        json_data = {"other": "data", "number": 42}
        raw_stdout = json.dumps(json_data)
        mock_env = Mock()
        mock_env.execute.return_value = Mock(
            return_code=0, stdout=raw_stdout, stderr=""
        )

        with patch('microbots.llm.openai_api.OpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test prompt",
                environment=mock_env,
            )

        call_count = [0]
        captured_output = [None]

        def mock_ask(message: str):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMAskResponse(command="echo test", task_done=False, thoughts="running")
            else:
                captured_output[0] = message
                return LLMAskResponse(command="", task_done=True, thoughts="done")

        bot.llm.ask = mock_ask

        result = bot.run("test task", max_iterations=5, timeout_in_seconds=60)

        assert result.status is True
        # Without "content" key, raw stdout is preserved
        assert captured_output[0] == raw_stdout

    def test_run_non_json_output_json_decode_error(self):
        """Test anthropic-text-editor hack: non-JSON stdout triggers JSONDecodeError, raw stdout kept."""
        raw_stdout = "this is plain text, not JSON"
        mock_env = Mock()
        mock_env.execute.return_value = Mock(
            return_code=0, stdout=raw_stdout, stderr=""
        )

        with patch('microbots.llm.openai_api.OpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test prompt",
                environment=mock_env,
            )

        call_count = [0]
        captured_output = [None]

        def mock_ask(message: str):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMAskResponse(command="echo test", task_done=False, thoughts="running")
            else:
                captured_output[0] = message
                return LLMAskResponse(command="", task_done=True, thoughts="done")

        bot.llm.ask = mock_ask

        result = bot.run("test task", max_iterations=5, timeout_in_seconds=60)

        assert result.status is True
        # JSONDecodeError is caught silently, raw stdout preserved
        assert captured_output[0] == raw_stdout

    def test_run_json_parse_blanket_exception(self, caplog):
        """Test anthropic-text-editor hack: blanket exception during JSON parsing logs warning and keeps raw stdout."""
        raw_stdout = '{"content": "valid json"}'
        mock_env = Mock()
        mock_env.execute.return_value = Mock(
            return_code=0, stdout=raw_stdout, stderr=""
        )

        with patch('microbots.llm.openai_api.OpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test prompt",
                environment=mock_env,
            )

        call_count = [0]
        captured_output = [None]

        def mock_ask(message: str):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMAskResponse(command="echo test", task_done=False, thoughts="running")
            else:
                captured_output[0] = message
                return LLMAskResponse(command="", task_done=True, thoughts="done")

        bot.llm.ask = mock_ask

        caplog.set_level(logging.WARNING)
        with patch('microbots.MicroBot.json.loads', side_effect=TypeError("test type error")):
            result = bot.run("test task", max_iterations=5, timeout_in_seconds=60)

        assert result.status is True
        # Blanket exception caught, raw stdout preserved
        assert captured_output[0] == raw_stdout
        # Warning should be logged
        assert "Failed to parse command output as JSON, using raw stdout" in caplog.text

    def test_explicit_token_provider_is_stored(self):
        """When token_provider is passed explicitly it is stored as-is, regardless of env."""
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")
        my_provider = Mock(return_value="tok")

        with patch('microbots.llm.openai_api.AzureOpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test",
                environment=mock_env,
                token_provider=my_provider,
            )

        assert bot.token_provider is my_provider

    def test_azure_ad_env_creates_token_provider_for_openai(self):
        """When AZURE_AUTH_METHOD=azure_ad and provider is openai, token_provider is auto-created."""
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")
        mock_credential = Mock()
        mock_provider = Mock()

        with patch.dict('os.environ', {'AZURE_AUTH_METHOD': 'azure_ad'}), \
             patch('microbots.MicroBot.DefaultAzureCredential', return_value=mock_credential), \
             patch('microbots.MicroBot.get_bearer_token_provider', return_value=mock_provider) as mock_gbtp, \
             patch('microbots.llm.openai_api.AzureOpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test",
                environment=mock_env,
            )

        mock_gbtp.assert_called_once_with(
            mock_credential, "https://cognitiveservices.azure.com/.default"
        )
        assert bot.token_provider is mock_provider

    def test_azure_ad_env_does_not_create_token_provider_for_anthropic(self):
        """When AZURE_AUTH_METHOD=azure_ad but provider is anthropic, no auto token_provider is created."""
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        with patch.dict('os.environ', {'AZURE_AUTH_METHOD': 'azure_ad'}), \
             patch('microbots.MicroBot.DefaultAzureCredential') as mock_cred_cls, \
             patch('microbots.llm.anthropic_api.Anthropic'):
            bot = MicroBot(
                model="anthropic/claude-sonnet-4-5",
                system_prompt="test",
                environment=mock_env,
            )

        mock_cred_cls.assert_not_called()
        assert bot.token_provider is None

    def test_no_azure_ad_env_leaves_token_provider_none(self):
        """When AZURE_AUTH_METHOD is not set, token_provider defaults to None."""
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="", stderr="")

        env_without_azure = {k: v for k, v in os.environ.items() if k != 'AZURE_AUTH_METHOD'}
        with patch.dict('os.environ', env_without_azure, clear=True), \
             patch('microbots.llm.openai_api.OpenAI'):
            bot = MicroBot(
                model="azure-openai/test-model",
                system_prompt="test",
                environment=mock_env,
            )

        assert bot.token_provider is None


@pytest.mark.integration
@pytest.mark.docker
class TestMicrobotToolInstallation:
    """Functional tests for MicroBot's tool installation capability."""

    @pytest.fixture(scope="function")
    def cscope_tool(self):
        """Load the cscope tool from YAML definition."""
        from microbots.tools.tool_yaml_parser import parse_tool_definition
        return parse_tool_definition("cscope.yaml")

    @pytest.fixture(scope="function")
    def c_code_repo(self, tmpdir):
        """Create a temporary C code repository for testing cscope."""
        repo_path = tmpdir.mkdir("c_project")

        # Create main.c
        main_c = repo_path.join("main.c")
        main_c.write("""
#include <stdio.h>
#include "utils.h"

int main() {
    int result = add_numbers(5, 3);
    printf("Result: %d\\n", result);
    return 0;
}
""")

        # Create utils.h
        utils_h = repo_path.join("utils.h")
        utils_h.write("""
#ifndef UTILS_H
#define UTILS_H

int add_numbers(int a, int b);
int multiply_numbers(int a, int b);

#endif
""")

        # Create utils.c
        utils_c = repo_path.join("utils.c")
        utils_c.write("""
#include "utils.h"

int add_numbers(int a, int b) {
    return a + b;
}

int multiply_numbers(int a, int b) {
    return a * b;
}
""")

        yield Path(str(repo_path))

        # Cleanup
        if repo_path.exists():
            subprocess.run(["rm", "-rf", str(repo_path)])

    @pytest.mark.ollama_local
    def test_cscope_tool_install_and_verify(self, cscope_tool, c_code_repo):
        """Test that cscope tool can be installed and verified in MicroBot environment."""
        from microbots.tools.internal_tool import Tool

        assert cscope_tool is not None
        assert isinstance(cscope_tool, Tool)
        assert cscope_tool.name == "cscope"

        # Create mount for the C code repository
        c_repo_mount = Mount(
            str(c_code_repo),
            f"{DOCKER_WORKING_DIR}/{c_code_repo.name}",
            PermissionLabels.READ_ONLY
        )

        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')

        # Create MicroBot with cscope tool
        bot = MicroBot(
            model=f"ollama-local/{local_model}",
            system_prompt="You are a helpful assistant.",
            folder_to_mount=c_repo_mount,
            additional_tools=[cscope_tool],
        )

        try:
            # Verify cscope is installed by checking version
            result = bot.environment.execute("cscope -V")
            assert result.return_code == 0, f"cscope -V failed: {result.stderr}"
            # cscope -V outputs to stderr, check either stdout or stderr
            assert "cscope" in result.stdout.lower() or "cscope" in result.stderr.lower(), \
                f"cscope version output not found. stdout: {result.stdout}, stderr: {result.stderr}"

            logger.info("cscope installation verified successfully")
        finally:
            del bot

    @pytest.mark.ollama_local
    def test_cscope_tool_setup_and_usage(self, cscope_tool, c_code_repo):
        """Test that cscope tool can be set up and used for code navigation."""
        # Create mount for the C code repository
        c_repo_mount = Mount(
            str(c_code_repo),
            f"{DOCKER_WORKING_DIR}/{c_code_repo.name}",
            PermissionLabels.READ_ONLY
        )

        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen3:latest').replace(':latest', '')
        bot = MicroBot(
            model=f"ollama-local/{local_model}",
            system_prompt="You are a helpful assistant.",
            folder_to_mount=c_repo_mount,
            additional_tools=[cscope_tool],
        )

        try:
            # Setup the tool (this runs setup_commands which builds cscope database)
            cscope_tool.setup_tool(bot.environment)

            # Change to the mounted directory and verify cscope database was created
            work_dir = f"{DOCKER_WORKING_DIR}/{c_code_repo.name}"
            result = bot.environment.execute(f"cd {work_dir} && ls -la cscope.out")
            assert result.return_code == 0, f"cscope.out not found: {result.stderr}"

            # Test cscope query: Find definition of add_numbers function (-1 flag)
            result = bot.environment.execute(f"cd {work_dir} && cscope -L -1 add_numbers")
            assert result.return_code == 0, f"cscope query failed: {result.stderr}"
            assert "add_numbers" in result.stdout, f"Function not found in cscope output: {result.stdout}"

            # Test cscope query: Find functions calling add_numbers (-3 flag)
            result = bot.environment.execute(f"cd {work_dir} && cscope -L -3 add_numbers")
            assert result.return_code == 0, f"cscope caller query failed: {result.stderr}"
            # add_numbers is called from main.c
            assert "main" in result.stdout.lower(), f"Caller not found: {result.stdout}"

            # Test cscope query: Find text string (-4 flag)
            result = bot.environment.execute(f"cd {work_dir} && cscope -L -4 'return a + b'")
            assert result.return_code == 0, f"cscope text search failed: {result.stderr}"
            assert "utils.c" in result.stdout, f"Text not found in expected file: {result.stdout}"

            logger.info("cscope tool usage verified successfully")
        finally:
            del bot

    def test_tool_install_failure_raises_error(self):
        """Test that tool installation failure raises appropriate error."""
        from microbots.tools.internal_tool import Tool

        # Create a tool with a failing install command
        failing_tool = Tool(
            name="failing_tool",
            description="A tool that fails to install",
            usage_instructions_to_llm="This tool will fail.",
            install_commands=["apt-get install -y nonexistent-package-xyz123"],
            env_variables=[],
            files_to_copy=[],
        )

        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')
        with pytest.raises(RuntimeError, match="Failed to install tool"):
            MicroBot(
                model=f"ollama-local/{local_model}",
                system_prompt="You are a helpful assistant.",
                additional_tools=[failing_tool],
            )

    def test_tool_verify_failure_raises_error(self):
        """Test that tool verification failure raises appropriate error."""
        from microbots.tools.internal_tool import Tool

        # Create a tool that installs but fails verification
        bad_verify_tool = Tool(
            name="bad_verify_tool",
            description="A tool that fails verification",
            usage_instructions_to_llm="This tool verification will fail.",
            install_commands=["echo 'installed'"],  # Installs successfully
            verify_commands=["nonexistent_command_abc123"],  # Fails verification
            env_variables=[],
            files_to_copy=[],
        )

        local_model = os.getenv('LOCAL_MODEL_NAME', 'qwen2.5-coder:latest').replace(':latest', '')
        with pytest.raises(RuntimeError, match="Failed to verify installation"):
            MicroBot(
                model=f"ollama-local/{local_model}",
                system_prompt="You are a helpful assistant.",
                additional_tools=[bad_verify_tool],
            )

    def test_tool_usage_instructions_in_system_prompt(self, cscope_tool):
        """Test that tool usage instructions are appended to the bot's system prompt."""
        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0, stdout="cscope: version 15.9", stderr="")

        base_prompt = "You are a code analysis assistant."

        with patch.dict('os.environ', {'LOCAL_MODEL_NAME': 'test-model', 'LOCAL_MODEL_PORT': '11434'}), \
             patch('microbots.llm.ollama_local.requests'):
            bot = MicroBot(
                model="ollama-local/test-model",
                system_prompt=base_prompt,
                additional_tools=[cscope_tool],
                environment=mock_env,
            )

            # Verify the cscope usage instructions are in the system prompt
            assert base_prompt in bot.llm.system_prompt
            assert "cscope" in bot.llm.system_prompt.lower()
            assert "-L" in bot.llm.system_prompt  # Non-interactive flag mentioned
            assert "batch mode" in bot.llm.system_prompt.lower() or "non-interactive" in bot.llm.system_prompt.lower()

    @pytest.mark.integration
    @pytest.mark.docker
    def test_llm_finds_symbols_using_cscope(self, cscope_tool, c_code_repo):
        """End-to-end test: LLM uses cscope to find symbol definitions and callers in C code."""
        c_repo_mount = Mount(
            str(c_code_repo),
            f"{DOCKER_WORKING_DIR}/{c_code_repo.name}",
            PermissionLabels.READ_ONLY
        )

        cscope_system_prompt = f"""
You are a C code analyst. You have a C project mounted at {DOCKER_WORKING_DIR}/{c_code_repo.name}.
The cscope tool is installed and its database has been built for you.
You MUST use cscope non-interactive batch mode commands (cscope -L <flag> <symbol>) to answer questions.
Always cd to {DOCKER_WORKING_DIR}/{c_code_repo.name} before running cscope commands.
Do not run interactive commands. Do not rebuild the database.

{llm_output_format_str}

You must send `task_done` as true only when you have found all the requested information.
Put your final answer in the `thoughts` field. The answer MUST include:
1. The file and function where `add_numbers` is defined
2. Which function(s) call `add_numbers`
"""

        bot = MicroBot(
            model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}",
            system_prompt=cscope_system_prompt,
            folder_to_mount=c_repo_mount,
            additional_tools=[cscope_tool],
        )

        try:
            response: BotRunResult = bot.run(
                f"Using cscope, find: (1) where the function `add_numbers` is defined, and (2) which functions call `add_numbers`. "
                f"The project is at {DOCKER_WORKING_DIR}/{c_code_repo.name}. Report your findings in the thoughts field.",
                timeout_in_seconds=1200,
                max_iterations=50,
            )

            logger.info(f"LLM cscope test - Status: {response.status}, Result: {response.result}, Error: {response.error}")

            assert response.status, f"Task failed. Error: {response.error}"
            assert response.error is None
            assert response.result is not None

            # The LLM should have found that add_numbers is defined in utils.c
            # and called from main (in main.c)
            result_lower = response.result.lower()
            assert "utils.c" in result_lower or "utils" in result_lower, \
                f"LLM should have found add_numbers defined in utils.c. Got: {response.result}"
            assert "main" in result_lower, \
                f"LLM should have found that main() calls add_numbers. Got: {response.result}"
        finally:
            del bot
