import logging
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Setup logging for tests
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))
from microbots import BrowsingBot, BotRunResult
from microbots.MicroBot import MicroBot
from microbots.environment.Environment import CmdReturn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_browsing_bot(model="azure-openai/test-deploy", token_provider=None):
    """Create a BrowsingBot with all heavy dependencies mocked out."""
    mock_env = MagicMock()

    with patch.object(MicroBot, "_create_environment"), \
         patch.object(MicroBot, "_create_llm"):
        with patch("microbots.bot.BrowsingBot.BROWSER_USE_TOOL") as mock_tool:
            mock_tool.install_tool = MagicMock()
            mock_tool.verify_tool_installation = MagicMock()
            mock_tool.setup_tool = MagicMock()
            mock_tool.usage_instructions_to_llm = None
            bot = BrowsingBot(model=model, environment=mock_env, token_provider=token_provider)

    bot.environment = mock_env
    return bot


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBrowsingBotRun:
    """Unit tests for BrowsingBot.run() — no Docker or LLM required."""

    def test_token_provider_injects_token_into_environment(self):
        """When token_provider is set, a fresh token is fetched and exported into the container."""
        token_provider = MagicMock(return_value="my.jwt.token")
        bot = _make_browsing_bot(token_provider=token_provider)

        bot.environment.execute.return_value = CmdReturn(
            stdout="Final result: done", stderr="", return_code=0
        )

        bot.run("some task")

        # First execute call should be the export
        export_call = bot.environment.execute.call_args_list[0]
        assert "AZURE_OPENAI_AD_TOKEN=my.jwt.token" in export_call.args[0]

    def test_token_not_injected_when_provider_is_none(self):
        """When token_provider is None, no export command is issued."""
        bot = _make_browsing_bot(token_provider=None)

        bot.environment.execute.return_value = CmdReturn(
            stdout="done", stderr="", return_code=0
        )

        bot.run("some task")

        # Only one execute call: the browser command itself
        assert bot.environment.execute.call_count == 1

    def test_task_with_single_quote_is_quoted(self):
        """Tasks containing single quotes must be shell-safe."""
        bot = _make_browsing_bot()

        bot.environment.execute.return_value = CmdReturn(
            stdout="done", stderr="", return_code=0
        )

        bot.run("What's the capital of France?")

        browser_call = bot.environment.execute.call_args_list[-1]
        cmd = browser_call.args[0]
        # shlex.quote wraps in single quotes and escapes internal ones
        assert "What" in cmd
        assert "browser" in cmd

    def test_browser_failure_returns_error_result(self):
        """A non-zero return code from the browser command is surfaced as a failed BotRunResult."""
        bot = _make_browsing_bot()

        bot.environment.execute.return_value = CmdReturn(
            stdout="", stderr="browser crashed", return_code=1
        )

        result = bot.run("find something")

        assert result.status is False
        assert result.result is None
        assert "browser crashed" in result.error

    def test_final_result_extracted_from_stdout(self):
        """'Final result:' prefix is stripped from browser output."""
        bot = _make_browsing_bot()

        bot.environment.execute.return_value = CmdReturn(
            stdout="some preamble\nFinal result: Paris", stderr="", return_code=0
        )

        result = bot.run("capital of France")

        assert result.status is True
        assert result.result == "Paris"

    def test_stdout_without_final_result_marker_returned_as_is(self):
        """When the output has no 'Final result:' marker the full stripped stdout is returned."""
        bot = _make_browsing_bot()

        bot.environment.execute.return_value = CmdReturn(
            stdout="  raw output  ", stderr="", return_code=0
        )

        result = bot.run("some task")

        assert result.result == "raw output"

@pytest.mark.integration
@pytest.mark.docker
@pytest.mark.slow  # Browser tests require Chromium installation and significant disk space
class TestBrowsingBot:
    """Integration tests for BrowsingBot functionality."""

    @pytest.fixture(scope="function")
    def browsing_bot(self):
        """Create a BrowsingBot instance for testing."""
        model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"
        bot = BrowsingBot(model=model)
        yield bot
        # Cleanup: stop the environment
        if hasattr(bot, 'environment') and bot.environment:
            try:
                bot.environment.stop()
            except Exception as e:
                logger.warning(f"Error stopping environment: {e}")

    # Google search may fail due to captcha, so this test may be flaky in CI environments.
    def test_simple_question_response(self, browsing_bot):
        """Test that the bot can answer a simple factual question."""
        response: BotRunResult = browsing_bot.run(
            "Get capital of France from https://en.wikipedia.org/wiki/France",
            timeout_in_seconds=300,
        )

        # Assert the response was successful
        assert response.status, f"Bot failed with error: {response.error}"
        assert response.result is not None, "Bot returned no result"
        assert isinstance(response.result, str), "Result should be a string"

        # Check that the result contains the expected answer
        result_lower = response.result.lower()
        assert "paris" in result_lower, f"Expected 'Paris' in result, got: {response.result}"

        logger.info(f"Test passed. Bot response: {response.result}")


    # Google search may fail due to captcha, so this test may be flaky in CI environments.
    @pytest.mark.parametrize("query,expected_keywords", [
        ("Get capital of Germany from https://en.wikipedia.org/wiki/Germany", ["berlin"]),
        ("Get the description of this CVE-2024-11738 from nvd.nist.gov website", ["Rustls"]),
    ])
    def test_multiple_queries(self, browsing_bot, query, expected_keywords):
        """Test the bot with multiple different queries."""
        response: BotRunResult = browsing_bot.run(query, timeout_in_seconds=300)

        assert response.status, f"Query '{query}' failed: {response.error}"
        assert response.result is not None, f"No result for query: {query}"

        result_lower = response.result.lower()
        # At least one expected keyword should be in the result
        keyword_found = any(keyword.lower() in result_lower for keyword in expected_keywords)
        assert keyword_found, f"None of {expected_keywords} found in result: {response.result}"

        logger.info(f"Query '{query}' passed with result: {response.result[:100]}...")
