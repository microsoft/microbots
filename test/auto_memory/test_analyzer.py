"""Unit tests for microbots.auto_memory.analyzer."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.analyzer import build_feedback
from microbots.auto_memory.evalTask import CallbackResult, EvalOutcome
from microbots.MicroBot import BotRunResult


def _make_outcome(reason: str = "tests failed", output: str = "agent output") -> EvalOutcome:
    return EvalOutcome(
        passed=False,
        output=output,
        result=CallbackResult(passed=False, reason=reason),
        log_path="/tmp/some.log",
    )


@pytest.mark.unit
@patch("microbots.auto_memory.analyzer.LogAnalysisBot")
def test_build_feedback_returns_bot_result_on_success(mock_bot_cls):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(
        status=True, result="root cause: missing edge case handling", error=None
    )
    mock_bot_cls.return_value = mock_bot

    outcome = _make_outcome()
    feedback = build_feedback(task=MagicMock(), outcome=outcome, repo_path="/repo", model="azure-openai/gpt-4o")

    assert feedback == "root cause: missing edge case handling"
    mock_bot_cls.assert_called_once_with(model="azure-openai/gpt-4o", folder_to_mount="/repo")
    mock_bot.run.assert_called_once()
    assert mock_bot.run.call_args.kwargs["file_name"] == outcome.log_path


@pytest.mark.unit
@patch("microbots.auto_memory.analyzer.LogAnalysisBot")
def test_build_feedback_falls_back_when_bot_status_false(mock_bot_cls):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=False, result=None, error="bot crashed")
    mock_bot_cls.return_value = mock_bot

    outcome = _make_outcome(reason="tests failed", output="some output")
    feedback = build_feedback(task=MagicMock(), outcome=outcome, repo_path="/repo", model="azure-openai/gpt-4o")

    assert "some output" in feedback
    assert "tests failed" in feedback


@pytest.mark.unit
@patch("microbots.auto_memory.analyzer.LogAnalysisBot")
def test_build_feedback_falls_back_when_result_is_empty(mock_bot_cls):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="", error=None)
    mock_bot_cls.return_value = mock_bot

    outcome = _make_outcome(reason="assertion error", output="agent tried X")
    feedback = build_feedback(task=MagicMock(), outcome=outcome, repo_path="/repo", model="azure-openai/gpt-4o")

    assert "agent tried X" in feedback
    assert "assertion error" in feedback


@pytest.mark.unit
@patch("microbots.auto_memory.analyzer.LogAnalysisBot")
def test_build_feedback_falls_back_when_result_is_none(mock_bot_cls):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result=None, error=None)
    mock_bot_cls.return_value = mock_bot

    outcome = _make_outcome()
    feedback = build_feedback(task=MagicMock(), outcome=outcome, repo_path="/repo", model="azure-openai/gpt-4o")

    assert "Evaluation failed" in feedback
