"""
Unit tests for MicrobotSubAgent.

Every code path in ``microbot_sub_agent.py`` is exercised — defaults,
``is_invoked``, and every branch inside ``invoke`` — to achieve 100 %
line coverage.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src"))
)

from microbots.tools.tool_definitions.microbot_sub_agent import (
    MicrobotSubAgent,
    INSTRUCTIONS_TO_LLM,
)
from microbots.MicroBot import MicroBot, BotRunResult
from microbots.environment.Environment import CmdReturn
from microbots.tools.tool import TOOLTYPE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parent_bot(**overrides):
    """Create a lightweight mock that looks like a MicroBot to ``invoke``."""
    bot = MagicMock(spec=MicroBot)
    bot.model = overrides.get("model", "azure-openai/test-deploy")
    bot.max_iterations = overrides.get("max_iterations", 50)
    bot.iteration_count = overrides.get("iteration_count", 0)
    bot.environment = overrides.get("environment", MagicMock())
    bot.token_provider = overrides.get("token_provider", None)
    return bot


# ---------------------------------------------------------------------------
# Defaults / class-level attributes
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMicrobotSubAgentDefaults:

    def test_default_name(self):
        tool = MicrobotSubAgent()
        assert tool.name == "microbot_sub"

    def test_default_description(self):
        tool = MicrobotSubAgent()
        assert "sub-agent" in tool.description

    def test_default_usage_instructions(self):
        tool = MicrobotSubAgent()
        assert tool.usage_instructions_to_llm == INSTRUCTIONS_TO_LLM

    def test_default_install_commands_empty(self):
        tool = MicrobotSubAgent()
        assert tool.install_commands == []

    def test_tool_type_is_external(self):
        tool = MicrobotSubAgent()
        assert tool.tool_type == TOOLTYPE.EXTERNAL


# ---------------------------------------------------------------------------
# is_invoked
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsInvoked:

    def test_exact_match(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked("microbot_sub") is True

    def test_with_arguments(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked('microbot_sub --task "hello"') is True

    def test_leading_whitespace(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked("  microbot_sub --task 'x'") is True

    def test_different_command(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked("ls -la") is False

    def test_empty_string(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked("") is False

    def test_partial_name(self):
        tool = MicrobotSubAgent()
        assert tool.is_invoked("microbot") is False


# ---------------------------------------------------------------------------
# invoke — argument parsing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInvokeParsing:

    def test_parses_task_iterations_timeout(self):
        """All three flags are extracted correctly."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=100)

        cmd = 'microbot_sub --task "do stuff" --iterations 10 --timeout 60'

        with patch.object(MicroBot, "__init__", return_value=None) as mock_init, \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="done", error=None
             )):
            # MicroBot.__init__ is mocked, so we need to set iteration_count
            with patch.object(MicroBot, "iteration_count", 3, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 0

    def test_defaults_iterations_and_timeout(self):
        """If --iterations and --timeout are omitted, defaults (25 / 300) apply."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50)

        cmd = 'microbot_sub --task "just a task"'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="ok", error=None
             )) as mock_run:
            with patch.object(MicroBot, "iteration_count", 0, create=True):
                tool.invoke(cmd, parent)

        _, kwargs = mock_run.call_args
        assert kwargs["max_iterations"] == 25
        assert kwargs["timeout_in_seconds"] == 300

    def test_task_with_single_quotes(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50)

        cmd = "microbot_sub --task 'fix the bug'"

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="fixed", error=None
             )) as mock_run:
            with patch.object(MicroBot, "iteration_count", 0, create=True):
                result = tool.invoke(cmd, parent)

        called_task = mock_run.call_args[1]["task"]
        assert "fix the bug" in called_task
        assert result.return_code == 0

    def test_task_containing_flag_like_text(self):
        """Task descriptions containing '--iterations' or '--task' text must not break parsing."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50)

        cmd = 'microbot_sub --task "run with --iterations 5 and --timeout flag" --iterations 10'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="ok", error=None
             )) as mock_run:
            with patch.object(MicroBot, "iteration_count", 0, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 0
        called_task = mock_run.call_args[1]["task"]
        assert "run with --iterations 5 and --timeout flag" in called_task
        _, kwargs = mock_run.call_args
        assert kwargs["max_iterations"] == 10


# ---------------------------------------------------------------------------
# invoke — error paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInvokeErrors:

    def test_no_task_returns_error(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke("microbot_sub --iterations 5", parent)

        assert result.return_code == 1
        assert "No task specified" in result.stderr

    def test_zero_iterations_returns_error(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --iterations 0', parent)

        assert result.return_code == 1
        assert "positive integers" in result.stderr

    def test_negative_timeout_returns_error(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --timeout -1', parent)

        assert result.return_code == 1
        assert "positive integers" in result.stderr

    def test_negative_iterations_returns_error(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --iterations -5', parent)

        assert result.return_code == 1
        assert "positive integers" in result.stderr

    def test_exceeds_remaining_budget(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=10, iteration_count=8)

        result = tool.invoke('microbot_sub --task "x" --iterations 5', parent)

        assert result.return_code == 1
        assert "remain in the parent bot's budget" in result.stderr

    def test_non_integer_iterations_raises_value_error(self):
        """argparse raises ValueError (via _NoExitArgumentParser.error) for non-integer --iterations."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --iterations abc', parent)

        assert result.return_code == 1
        assert result.stderr.startswith("Error:")

    def test_non_integer_timeout_raises_value_error(self):
        """argparse raises ValueError (via _NoExitArgumentParser.error) for non-integer --timeout."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --timeout xyz', parent)

        assert result.return_code == 1
        assert result.stderr.startswith("Error:")

    def test_unrecognized_argument_raises_value_error(self):
        """argparse raises ValueError (via _NoExitArgumentParser.error) for unknown flags."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "x" --unknown flag', parent)

        assert result.return_code == 1
        assert result.stderr.startswith("Error:")

    def test_unclosed_quote_raises_value_error(self):
        """shlex.split raises ValueError for an unclosed quoted string."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot()

        result = tool.invoke('microbot_sub --task "unclosed quote', parent)

        assert result.return_code == 1
        assert result.stderr.startswith("Error:")


# ---------------------------------------------------------------------------
# invoke — success path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInvokeSuccess:

    def test_success_returns_stdout(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=0)

        cmd = 'microbot_sub --task "analyse logs" --iterations 10 --timeout 120'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="all clear", error=None
             )):
            with patch.object(MicroBot, "iteration_count", 4, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 0
        assert result.stdout == "all clear"
        assert result.stderr == ""

    def test_success_with_none_result(self):
        """When sub-bot result is None, stdout should be empty string."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=0)

        cmd = 'microbot_sub --task "silent task"'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result=None, error=None
             )):
            with patch.object(MicroBot, "iteration_count", 1, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 0
        assert result.stdout == ""

    def test_iteration_count_charged_to_parent(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=5)

        cmd = 'microbot_sub --task "work" --iterations 10'

        sub_iterations = 7

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="ok", error=None
             )):
            with patch.object(MicroBot, "iteration_count", sub_iterations, create=True):
                tool.invoke(cmd, parent)

        assert parent.iteration_count == 5 + sub_iterations

    def test_sub_bot_created_with_parent_model_and_env(self):
        tool = MicrobotSubAgent()
        mock_env = MagicMock()
        parent = _make_parent_bot(
            model="anthropic/claude-sonnet-4-5",
            environment=mock_env,
            max_iterations=50,
        )

        cmd = 'microbot_sub --task "check" --iterations 5'

        with patch.object(MicroBot, "__init__", return_value=None) as mock_init, \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=True, result="ok", error=None
             )):
            with patch.object(MicroBot, "iteration_count", 0, create=True):
                tool.invoke(cmd, parent)

        mock_init.assert_called_once()
        _, kwargs = mock_init.call_args
        assert kwargs["model"] == "anthropic/claude-sonnet-4-5"
        assert kwargs["environment"] is mock_env


# ---------------------------------------------------------------------------
# invoke — failure path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInvokeFailure:

    def test_failed_sub_agent_returns_error(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=0)

        cmd = 'microbot_sub --task "break things" --iterations 10'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=False, result="partial output", error="timeout reached"
             )):
            with patch.object(MicroBot, "iteration_count", 10, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 1
        assert "Sub-agent failed" in result.stderr
        assert "timeout reached" in result.stderr
        assert result.stdout == "partial output"

    def test_failed_sub_agent_with_none_result(self):
        """When sub-bot fails and result is None, stdout should be empty."""
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=0)

        cmd = 'microbot_sub --task "crash" --iterations 5'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=False, result=None, error="boom"
             )):
            with patch.object(MicroBot, "iteration_count", 5, create=True):
                result = tool.invoke(cmd, parent)

        assert result.return_code == 1
        assert result.stdout == ""

    def test_failed_sub_agent_charges_iterations(self):
        tool = MicrobotSubAgent()
        parent = _make_parent_bot(max_iterations=50, iteration_count=2)

        cmd = 'microbot_sub --task "fail" --iterations 10'

        with patch.object(MicroBot, "__init__", return_value=None), \
             patch.object(MicroBot, "run", return_value=BotRunResult(
                 status=False, result=None, error="err"
             )):
            with patch.object(MicroBot, "iteration_count", 8, create=True):
                tool.invoke(cmd, parent)

        assert parent.iteration_count == 2 + 8
