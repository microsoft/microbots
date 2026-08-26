"""Unit tests for microbots.auto_memory.task."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.task import CallbackResult, EvalOutcome, EvalTask
from microbots.MicroBot import BotRunResult


class _StubTask(EvalTask):
    """A minimal concrete EvalTask used to exercise the base run() logic."""

    def __init__(self, check_result=None, check_side_effect=None, build_prompt_side_effect=None):
        self.setup_calls = []
        self.teardown_calls = []
        self.check_calls = []
        self._check_result = check_result or CallbackResult(passed=True, reason="ok")
        self._check_side_effect = check_side_effect
        self._build_prompt_side_effect = build_prompt_side_effect

    def setup(self, repo_path):
        self.setup_calls.append(repo_path)

    def build_prompt(self, repo_path):
        if self._build_prompt_side_effect:
            raise self._build_prompt_side_effect
        return "do the task"

    def check(self, repo_path, agent_output, log_path):
        self.check_calls.append((repo_path, agent_output, log_path))
        if self._check_side_effect:
            raise self._check_side_effect
        return self._check_result

    def teardown(self, repo_path):
        self.teardown_calls.append(repo_path)


class _RaisingTeardownTask(_StubTask):
    def teardown(self, repo_path):
        super().teardown(repo_path)
        raise RuntimeError("teardown boom")


class _DefaultTeardownTask(EvalTask):
    """A task that relies on EvalTask's default no-op teardown."""

    def setup(self, repo_path):
        pass

    def build_prompt(self, repo_path):
        return "do the task"

    def check(self, repo_path, agent_output, log_path):
        return CallbackResult(passed=True, reason="ok")


@pytest.mark.unit
def test_setup_and_check_are_abstract():
    with pytest.raises(TypeError):
        EvalTask()


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_calls_setup_build_prompt_check_teardown_in_order(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="agent did stuff", error=None)
    mock_bot_cls.return_value = mock_bot

    task = _StubTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert task.setup_calls == ["/repo"]
    assert task.check_calls == [("/repo", "agent did stuff", outcome.log_path)]
    assert task.teardown_calls == ["/repo"]
    assert outcome.passed is True
    assert outcome.output == "agent did stuff"


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_creates_log_file_before_check_is_called(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    seen_log_exists = {}

    class _CheckingTask(_StubTask):
        def check(self, repo_path, agent_output, log_path):
            seen_log_exists["exists"] = os.path.exists(log_path)
            return super().check(repo_path, agent_output, log_path)

    task = _CheckingTask()
    task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert seen_log_exists["exists"] is True


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_skips_check_when_bot_status_is_false(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=False, result=None, error="bot crashed")
    mock_bot_cls.return_value = mock_bot

    task = _StubTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert task.check_calls == []
    assert outcome.passed is False
    assert "bot crashed" in outcome.result.reason


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_converts_build_prompt_exception_to_failed_outcome(mock_bot_cls, mock_memory_tool):
    task = _StubTask(build_prompt_side_effect=ValueError("bad prompt"))
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert outcome.passed is False
    assert "bad prompt" in outcome.result.reason
    with open(outcome.log_path) as f:
        assert "bad prompt" in f.read()


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_converts_check_exception_to_failed_outcome(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = _StubTask(check_side_effect=RuntimeError("check exploded"))
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert outcome.passed is False
    assert "check exploded" in outcome.result.reason


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_still_calls_teardown_when_body_raises(mock_bot_cls, mock_memory_tool):
    mock_bot_cls.side_effect = RuntimeError("bot construction failed")

    task = _StubTask()
    task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert task.teardown_calls == ["/repo"]


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_teardown_exception_does_not_clobber_returned_outcome(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = _RaisingTeardownTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    # teardown() raised, but the already-computed EvalOutcome must still be returned
    assert isinstance(outcome, EvalOutcome)
    assert outcome.passed is True


@pytest.mark.unit
@patch("microbots.auto_memory.task.MemoryTool")
@patch("microbots.auto_memory.task.WritingBot")
def test_run_uses_default_noop_teardown_when_not_overridden(mock_bot_cls, mock_memory_tool):
    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = _DefaultTeardownTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert outcome.passed is True

