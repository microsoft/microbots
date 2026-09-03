"""Unit tests for microbots.auto_memory.orchestrator."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.orchestrator import (
    LoopResult,
    clone_repo,
    run,
    run_train_eval_loop,
    run_training_loop,
    write_eval_result,
)
from microbots.auto_memory.evalTask import CallbackResult, EvalOutcome
from microbots.auto_memory.workdir import eval_result_path, memory_dir, round_memory_dir

MODULE = "microbots.auto_memory.orchestrator"


def _make_outcome(passed: bool, reason: str = "reason") -> EvalOutcome:
    return EvalOutcome(
        passed=passed,
        output="agent output",
        result=CallbackResult(passed=passed, reason=reason),
    )


def _touch(path: str) -> str:
    Path(path).write_text("log contents")
    return path


def _make_task() -> MagicMock:
    """A MagicMock task with a real-ish task_id/build_result, for round tests."""
    task = MagicMock()
    task.task_id = "task-1"
    task.build_result.side_effect = lambda outcome: {
        "passed": outcome.result.passed,
        "reason": outcome.result.reason,
    }
    return task


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_loop_returns_immediately_when_first_round_passes(mock_run_training_loop, tmp_path):
    task = _make_task()
    task.run.return_value = _make_outcome(passed=True)

    result = run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert isinstance(result, LoopResult)
    assert result.passed is True
    assert result.rounds_run == 1
    assert task.run.call_count == 1
    task.build_feedback.assert_not_called()
    mock_run_training_loop.assert_not_called()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_loop_retrains_and_continues_on_failure_then_passes(mock_run_training_loop, tmp_path):
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.return_value = "feedback text"

    result = run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    task.build_feedback.assert_called_once()
    mock_run_training_loop.assert_called_once_with(
        repo_path="/repo",
        feedback="feedback text",
        memory_dir=str(round_memory_dir(tmp_path, 1, instance_id="task-1")),
        model="azure-openai/gpt-4o",
        iterations=10,
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_loop_exhausts_max_rounds_without_passing(mock_run_training_loop, tmp_path):
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False)
        for i in range(3)
    ]
    task.build_feedback.return_value = "feedback text"

    result = run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=3)

    assert result.passed is False
    assert result.rounds_run == 3
    assert len(result.outcomes) == 3
    assert result.final_outcome is result.outcomes[-1]
    assert task.build_feedback.call_count == 3
    assert mock_run_training_loop.call_count == 3


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_log_path_persists_after_passing_round(mock_run_training_loop, tmp_path):
    log_path = _touch(str(tmp_path / "round1.log"))
    task = _make_task()
    task.run.return_value = _make_outcome(passed=True)

    run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert Path(log_path).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_log_path_persists_after_failing_round(mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    log2 = _touch(str(tmp_path / "round2.log"))
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.return_value = "feedback text"

    run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert Path(log1).exists()
    assert Path(log2).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_build_feedback_exception_does_not_crash_loop(mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.side_effect = RuntimeError("analysis bot crashed")

    result = run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    mock_run_training_loop.assert_not_called()
    assert Path(log1).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_loop_forwards_training_iterations_to_run_training_loop(mock_run_training_loop, tmp_path):
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.return_value = "feedback text"

    run_train_eval_loop(
        "/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5, training_iterations=4
    )

    mock_run_training_loop.assert_called_once_with(
        repo_path="/repo",
        feedback="feedback text",
        memory_dir=str(round_memory_dir(tmp_path, 1, instance_id="task-1")),
        model="azure-openai/gpt-4o",
        iterations=4,
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training_loop")
def test_run_training_exception_does_not_crash_loop(mock_run_training_loop, tmp_path):
    log1 = _touch(str(tmp_path / "round1.log"))
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.return_value = "feedback text"
    mock_run_training_loop.side_effect = RuntimeError("training crashed")

    result = run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert result.passed is True
    assert result.rounds_run == 2
    assert Path(log1).exists()


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training")
def test_run_training_loop_calls_run_training_ten_times_by_default(mock_run_training):
    run_training_loop(repo_path="/repo", feedback="fb", memory_dir="/memory", model="azure-openai/gpt-4o")

    assert mock_run_training.call_count == 10
    mock_run_training.assert_called_with(
        repo_path="/repo", feedback="fb", memory_dir="/memory", model="azure-openai/gpt-4o"
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training")
def test_run_training_loop_calls_run_training_n_times(mock_run_training):
    run_training_loop(
        repo_path="/repo", feedback="fb", memory_dir="/memory", model="azure-openai/gpt-4o", iterations=3
    )

    assert mock_run_training.call_count == 3
    mock_run_training.assert_called_with(
        repo_path="/repo", feedback="fb", memory_dir="/memory", model="azure-openai/gpt-4o"
    )


@pytest.mark.unit
@patch("microbots.auto_memory.orchestrator.run_training")
def test_run_training_loop_reuses_same_memory_dir_each_pass(mock_run_training):
    run_training_loop(
        repo_path="/repo", feedback="fb", memory_dir="/memory", model="azure-openai/gpt-4o", iterations=4
    )

    memory_dirs = {call.kwargs["memory_dir"] for call in mock_run_training.call_args_list}
    assert memory_dirs == {"/memory"}


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_clone_repo_clones_when_missing(mock_run, tmp_path):
    repo_path = tmp_path / "repo"

    clone_repo("https://example.com/repo.git", repo_path)

    mock_run.assert_called_once_with(
        ["git", "clone", "https://example.com/repo.git", str(repo_path)], check=True
    )


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_clone_repo_is_noop_when_already_present(mock_run, tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    clone_repo("https://example.com/repo.git", repo_path)

    mock_run.assert_not_called()


@pytest.mark.unit
def test_write_eval_result_writes_task_build_result_as_json(tmp_path):
    task = MagicMock()
    task.task_id = "django__django-1"
    task.build_result.return_value = {"passed": True, "reason": "resolved"}
    outcome = _make_outcome(passed=True)

    write_eval_result(tmp_path, 2, task, outcome)

    result_path = eval_result_path(tmp_path, 2, "django__django-1")
    assert json.loads(result_path.read_text()) == {"passed": True, "reason": "resolved"}
    task.build_result.assert_called_once_with(outcome)


@pytest.mark.unit
def test_write_eval_result_creates_missing_parent_dirs(tmp_path):
    task = MagicMock()
    task.task_id = "some-task"
    task.build_result.return_value = {"passed": False, "reason": "nope"}
    outcome = _make_outcome(passed=False)

    write_eval_result(tmp_path, 1, task, outcome)

    assert eval_result_path(tmp_path, 1, "some-task").exists()


@pytest.mark.unit
def test_loop_writes_eval_result_for_every_round(tmp_path):
    task = _make_task()
    task.run.side_effect = [
        _make_outcome(passed=False),
        _make_outcome(passed=True),
    ]
    task.build_feedback.return_value = "feedback text"

    with patch(f"{MODULE}.run_training_loop"):
        run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert eval_result_path(tmp_path, 1, "task-1").exists()
    assert eval_result_path(tmp_path, 2, "task-1").exists()
    assert json.loads(eval_result_path(tmp_path, 2, "task-1").read_text()) == {
        "passed": True,
        "reason": "reason",
    }


@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_run_calls_run_training_loop_when_task_is_none(mock_run_training_loop, tmp_path):
    result = run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None, training_iterations=2)

    mock_run_training_loop.assert_called_once_with(
        repo_path=str(tmp_path / "repo"),
        feedback="",
        memory_dir=str(round_memory_dir(tmp_path, 1)),
        model="azure-openai/gpt-4o",
        iterations=2,
    )
    assert result is None


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
def test_run_calls_run_train_eval_loop_when_task_given(mock_run_train_eval_loop, tmp_path):
    fake_task = MagicMock()
    mock_run_train_eval_loop.return_value = "loop-result"

    result = run(
        workdir=tmp_path,
        model="azure-openai/gpt-4o",
        task=fake_task,
        max_rounds=3,
        training_iterations=2,
    )

    mock_run_train_eval_loop.assert_called_once_with(
        training_repo_path=str(tmp_path / "repo"),
        eval_repo_path=str(tmp_path / "eval_repo"),
        workdir=tmp_path,
        model="azure-openai/gpt-4o",
        task=fake_task,
        max_rounds=3,
        training_iterations=2,
    )
    assert result == "loop-result"


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
@patch(f"{MODULE}.run_training_loop")
def test_run_does_not_call_eval_loop_when_task_is_none(mock_run_training_loop, mock_run_train_eval_loop, tmp_path):
    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None)

    mock_run_train_eval_loop.assert_not_called()


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
@patch(f"{MODULE}.run_training_loop")
def test_run_does_not_call_training_loop_when_task_given(mock_run_training_loop, mock_run_train_eval_loop, tmp_path):
    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=MagicMock())

    mock_run_training_loop.assert_not_called()


@pytest.mark.unit
@patch(f"{MODULE}.clone_repo")
@patch(f"{MODULE}.run_training_loop")
def test_run_clones_repo_from_config_when_repo_url_given(mock_run_training_loop, mock_clone_repo, tmp_path):
    (tmp_path / "config.yaml").write_text("repo: https://example.com/repo.git\n")

    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None)

    mock_clone_repo.assert_called_once_with("https://example.com/repo.git", tmp_path / "repo")


@pytest.mark.unit
@patch(f"{MODULE}.clone_repo")
@patch(f"{MODULE}.run_training_loop")
def test_run_does_not_clone_when_config_has_no_repo(mock_run_training_loop, mock_clone_repo, tmp_path):
    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None)

    mock_clone_repo.assert_not_called()


@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_run_promotes_round1_memory_to_top_level_for_train_only_mode(mock_run_training_loop, tmp_path):
    def fake_train(repo_path, feedback, memory_dir, model, iterations=1):
        Path(memory_dir, "notes.md").write_text("learned something")

    mock_run_training_loop.side_effect = fake_train

    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None)

    assert (memory_dir(tmp_path) / "notes.md").read_text() == "learned something"


@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_run_preserves_original_memory_as_a_seed_snapshot(mock_run_training_loop, tmp_path):
    memory_dir(tmp_path).mkdir(parents=True)
    (memory_dir(tmp_path) / "notes.md").write_text("original seed")

    def fake_train(repo_path, feedback, memory_dir, model, iterations=1):
        Path(memory_dir, "notes.md").write_text("overwritten by training")

    mock_run_training_loop.side_effect = fake_train

    run(workdir=tmp_path, model="azure-openai/gpt-4o", task=None)

    assert (memory_dir(tmp_path) / "notes.md").read_text() == "overwritten by training"
    assert (tmp_path / "memory_seed" / "notes.md").read_text() == "original seed"



@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_loop_carries_memory_forward_between_rounds(mock_run_training_loop, tmp_path):
    seen_memory_dirs = []

    def fake_run(repo_path, memory_dir, model, log_path):
        round_num = len(seen_memory_dirs) + 1
        if round_num == 2:
            # Round 2 should start with whatever round 1 saved.
            assert (Path(memory_dir) / "notes.md").read_text() == "round 1 progress"
        seen_memory_dirs.append(memory_dir)
        Path(memory_dir, "notes.md").write_text(f"round {round_num} progress")
        return _make_outcome(passed=round_num == 2)

    task = _make_task()
    task.run.side_effect = fake_run
    task.build_feedback.return_value = "feedback text"

    run_train_eval_loop("/repo", "/eval_repo", tmp_path, "azure-openai/gpt-4o", task, max_rounds=5)

    assert (memory_dir(tmp_path) / "notes.md").read_text() == "round 2 progress"
