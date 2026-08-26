"""Unit tests for microbots.auto_memory.orchestrator."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.orchestrator import LoopResult, run_train_eval_loop
from microbots.auto_memory.task import CallbackResult, EvalOutcome


def _make_outcome(passed: bool, log_path: str, reason: str = "reason") -> EvalOutcome:
    return EvalOutcome(
        passed=passed,
        output="agent output",
        result=CallbackResult(passed=passed, reason=reason),
        log_path=log_path,
    )


def _touch(path: str) -> str:
    Path(path).write_text("log contents")
    return path


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_loop_returns_immediately_when_first_round_passes(mock_build_feedback, mock_run_training_loop, tmp_path):
    log_path = _touch(str(tmp_path / "round1.log"))
    task = MagicMock()
    task.run.return_value = _make_outcome(passed=True, log_path=log_path)

    result = run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert isinstance(result, LoopResult)
    assert result.passed is True
    assert result.rounds_run == 1
    assert task.run.call_count == 1
    mock_build_feedback.assert_not_called()
    mock_run_training_loop.assert_not_called()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_loop_retrains_and_continues_on_failure_then_passes(mock_build_feedback, mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=log1),
        _make_outcome(passed=True, log_path=log2),
    ]
    mock_build_feedback.return_value = "feedback text"

    result = run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    mock_build_feedback.assert_called_once()
    mock_run_training_loop.assert_called_once_with(
        repo_path="/repo", feedback="feedback text", memory_dir="/memory", model="azure-openai/gpt-4o", iterations=1
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_loop_exhausts_max_rounds_without_passing(mock_build_feedback, mock_run_training_loop, tmp_path):
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=_touch(str(tmp_path / f"round{i}.log")))
        for i in range(3)
    ]
    mock_build_feedback.return_value = "feedback text"

    result = run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=3)

    assert result.passed is False
    assert result.rounds_run == 3
    assert len(result.outcomes) == 3
    assert result.final_outcome is result.outcomes[-1]
    assert mock_build_feedback.call_count == 3
    assert mock_run_training_loop.call_count == 3


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_log_path_deleted_after_passing_round(mock_build_feedback, mock_run_training_loop, tmp_path):
    log_path = _touch(str(tmp_path / "round1.log"))
    task = MagicMock()
    task.run.return_value = _make_outcome(passed=True, log_path=log_path)

    run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert not Path(log_path).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_log_path_deleted_after_failing_round(mock_build_feedback, mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=log1),
        _make_outcome(passed=True, log_path=log2),
    ]
    mock_build_feedback.return_value = "feedback text"

    run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert not Path(log1).exists()
    assert not Path(log2).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_build_feedback_exception_does_not_crash_loop(mock_build_feedback, mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=log1),
        _make_outcome(passed=True, log_path=log2),
    ]
    mock_build_feedback.side_effect = RuntimeError("analysis bot crashed")

    result = run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    mock_run_training_loop.assert_not_called()
    assert not Path(log1).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_loop_forwards_training_iterations_to_run_training_loop(mock_build_feedback, mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=log1),
        _make_outcome(passed=True, log_path=log2),
    ]
    mock_build_feedback.return_value = "feedback text"

    run_train_eval_loop(
        "/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5, training_iterations=4
    )

    mock_run_training_loop.assert_called_once_with(
        repo_path="/repo", feedback="feedback text", memory_dir="/memory", model="azure-openai/gpt-4o", iterations=4
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
@patch("microbots.auto_memory.orchestrator.build_feedback")
def test_run_training_exception_does_not_crash_loop(mock_build_feedback, mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = MagicMock()
    task.run.side_effect = [
        _make_outcome(passed=False, log_path=log1),
        _make_outcome(passed=True, log_path=log2),
    ]
    mock_build_feedback.return_value = "feedback text"
    mock_run_training_loop.side_effect = RuntimeError("training crashed")

    result = run_train_eval_loop("/repo", "/memory", "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    assert not Path(log1).exists()
