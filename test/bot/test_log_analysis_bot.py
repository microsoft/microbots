"""
This test uses the LogAnalysisBot to analyze logs from a failing run mentioned in
https://github.com/SWE-agent/test-repo/issues/1
The issue is a simple syntax correction issue from original SWE-bench's test-repo.
"""

import os
import subprocess
import sys

import pytest
from unittest.mock import patch, MagicMock

# Add src directory to path to import from local source
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from microbots import LogAnalysisBot, BotRunResult
from microbots.MicroBot import MicroBot
from microbots.tools.tool import ToolAbstract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log_bot(model="azure-openai/test-deploy", additional_tools=None, token_provider=None):
    """Create a LogAnalysisBot with Docker and LLM mocked out."""
    mock_env = MagicMock()

    with patch.object(MicroBot, "_create_environment"), \
         patch.object(MicroBot, "_create_llm"):
        bot = LogAnalysisBot(
            model=model,
            folder_to_mount="/tmp/fake-repo",
            environment=mock_env,
            additional_tools=additional_tools,
            token_provider=token_provider,
        )

    bot.environment = mock_env
    return bot


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLogAnalysisBotUnit:
    """Unit tests for LogAnalysisBot.__init__ — no Docker or LLM required."""

    def test_default_additional_tools_is_empty_list(self):
        """When additional_tools is not passed, the bot has an empty tools list."""
        bot = _make_log_bot()
        assert bot.additional_tools == []

    def test_none_additional_tools_normalised_to_empty_list(self):
        """Passing additional_tools=None explicitly should also yield an empty list."""
        bot = _make_log_bot(additional_tools=None)
        assert bot.additional_tools == []

    def test_additional_tools_passed_through(self):
        """User-supplied tools are stored on the bot."""
        extra_tool = MagicMock(spec=ToolAbstract)
        extra_tool.install_tool = MagicMock()
        extra_tool.verify_tool_installation = MagicMock()
        extra_tool.usage_instructions_to_llm = None

        bot = _make_log_bot(additional_tools=[extra_tool])
        assert extra_tool in bot.additional_tools

    def test_two_instances_do_not_share_tools_list(self):
        """Each instance must get its own list — no shared mutable default."""
        bot1 = _make_log_bot()
        bot2 = _make_log_bot()
        assert bot1.additional_tools is not bot2.additional_tools

    def test_token_provider_stored(self):
        """An explicit token_provider is forwarded to MicroBot."""
        provider = MagicMock(return_value="tok")
        bot = _make_log_bot(token_provider=provider)
        assert bot.token_provider is provider

    def test_system_prompt_contains_log_file_dir(self):
        """The system prompt must reference the log file directory."""
        from microbots.constants import LOG_FILE_DIR
        bot = _make_log_bot()
        assert LOG_FILE_DIR in bot.system_prompt

    def test_folder_mount_sandbox_path_uses_basename(self):
        """The sandbox path is derived from the basename of folder_to_mount."""
        from microbots.constants import DOCKER_WORKING_DIR
        bot = _make_log_bot()
        assert bot.folder_to_mount.sandbox_path == f"/{DOCKER_WORKING_DIR}/fake-repo"

@pytest.mark.integration
@pytest.mark.docker

class TestLogAnalysisBot:

    @pytest.fixture(scope="function")
    def log_file_path(self, tmpdir):
        assert tmpdir.exists()
        yield tmpdir / "error.log"
        if tmpdir.exists():
            subprocess.run(["rm", "-rf", str(tmpdir)])

    @pytest.fixture(scope="function")
    def log_analysis_bot(self, test_repo):
        model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"
        log_analysis_bot = LogAnalysisBot(
            model=model,
            folder_to_mount=str(test_repo)
        )

        yield log_analysis_bot

        # Cleanup: stop the environment
        if hasattr(log_analysis_bot, 'environment') and log_analysis_bot.environment:
            try:
                log_analysis_bot.environment.stop()
            except Exception as e:
                logger.warning(f"Error stopping environment: {e}")

    @pytest.mark.slow
    def test_log_analysis_bot(self, log_analysis_bot, log_file_path, test_repo, issue_1):
        assert log_analysis_bot is not None

        run_function = issue_1[2]

        try:
            result = run_function(test_repo)
        except Exception as e:
            pytest.fail(f"Failed to run function to generate logs: {e}")

        assert result.returncode != 0
        assert result.stderr is not None

        with open(log_file_path, "w") as log_file:
            log_file.write(result.stderr)

        response: BotRunResult = log_analysis_bot.run(
            str(log_file_path), timeout_in_seconds=300
        )

        print(f"Status: {response.status}, Result: {response.result}, Error: {response.error}")

        assert response.status
        assert response.result is not None
        assert response.error is None

    def test_log_analysis_bot_nonexistent_file(self, log_analysis_bot):
        assert log_analysis_bot is not None

        fake_log_file = "non_existent.log"

        with pytest.raises(ValueError, match="Failed to copy additional mount to container"):
            log_analysis_bot.run(
                fake_log_file, timeout_in_seconds=60
            )

        logger.info("Successfully caught expected ValueError for nonexistent log file")

    @pytest.mark.slow
    def test_log_analysis_bot_max_iterations(self, log_analysis_bot, log_file_path, test_repo, issue_1):
        """Test that max_iterations parameter limits the number of iterations"""
        assert log_analysis_bot is not None

        run_function = issue_1[2]

        try:
            result = run_function(test_repo)
        except Exception as e:
            pytest.fail(f"Failed to run function to generate logs: {e}")

        assert result.returncode != 0
        assert result.stderr is not None

        with open(log_file_path, "w") as log_file:
            log_file.write(result.stderr)

        # Run with a very low max_iterations to force it to hit the limit
        response: BotRunResult = log_analysis_bot.run(
            str(log_file_path), max_iterations=2, timeout_in_seconds=300
        )

        print(f"Status: {response.status}, Result: {response.result}, Error: {response.error}")

        # Should fail due to max iterations being reached
        assert response.status is False
        assert response.error is not None
        assert "Max iterations 2 reached" in response.error

        logger.info("Successfully verified max_iterations parameter limits execution")
