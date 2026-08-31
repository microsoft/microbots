"""Unit tests for microbots.auto_memory.cli."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.cli import main, parse_args

MODULE = "microbots.auto_memory.cli"

BASE_ARGS = ["--repo", "/repo", "--memory-dir", "/memory", "--model", "azure-openai/gpt-4o"]


@pytest.mark.unit
def test_parse_args_defaults():
    args = parse_args(BASE_ARGS)

    assert args.repo == "/repo"
    assert args.memory_dir == "/memory"
    assert args.model == "azure-openai/gpt-4o"
    assert args.task is None
    assert args.max_rounds == 5
    assert args.training_iterations == 1


@pytest.mark.unit
def test_parse_args_with_known_task_adds_its_flags():
    args = parse_args(BASE_ARGS + ["--task", "swebenchverified", "--instance-id", "django__django-1"])

    assert args.task == "swebenchverified"
    assert args.instance_id == "django__django-1"


@pytest.mark.unit
def test_parse_args_rejects_unknown_task():
    with pytest.raises(SystemExit):
        parse_args(BASE_ARGS + ["--task", "does-not-exist"])


@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_main_runs_training_only_when_task_omitted(mock_run_training_loop):
    main(BASE_ARGS)

    mock_run_training_loop.assert_called_once_with(
        repo_path="/repo",
        feedback="",
        memory_dir="/memory",
        model="azure-openai/gpt-4o",
        iterations=1,
    )


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
@patch(f"{MODULE}.run_training_loop")
def test_main_does_not_run_eval_loop_when_task_omitted(mock_run_training_loop, mock_run_train_eval_loop):
    main(BASE_ARGS)

    mock_run_train_eval_loop.assert_not_called()


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
def test_main_runs_eval_loop_for_each_task_when_task_given(mock_run_train_eval_loop):
    fake_task = MagicMock()
    mock_run_train_eval_loop.return_value = MagicMock(passed=True, rounds_run=1)

    with patch(f"{MODULE}.TASK_REGISTRY", {"swebenchverified": MagicMock(from_cli_args=lambda args: [fake_task])}):
        main(BASE_ARGS + ["--task", "swebenchverified"])

    mock_run_train_eval_loop.assert_called_once_with(
        repo_path="/repo",
        memory_dir="/memory",
        model="azure-openai/gpt-4o",
        task=fake_task,
        max_rounds=5,
        training_iterations=1,
    )


@pytest.mark.unit
@patch(f"{MODULE}.run_training_loop")
def test_main_does_not_run_training_only_path_when_task_given(mock_run_training_loop):
    fake_task = MagicMock()

    with patch(f"{MODULE}.TASK_REGISTRY", {"swebenchverified": MagicMock(from_cli_args=lambda args: [fake_task])}):
        with patch(f"{MODULE}.run_train_eval_loop") as mock_run_train_eval_loop:
            mock_run_train_eval_loop.return_value = MagicMock(passed=True, rounds_run=1)
            main(BASE_ARGS + ["--task", "swebenchverified"])

    mock_run_training_loop.assert_not_called()


@pytest.mark.unit
@patch(f"{MODULE}.run_train_eval_loop")
def test_main_runs_eval_loop_once_per_returned_task(mock_run_train_eval_loop):
    fake_tasks = [MagicMock(), MagicMock()]
    mock_run_train_eval_loop.return_value = MagicMock(passed=False, rounds_run=5)

    with patch(f"{MODULE}.TASK_REGISTRY", {"swebenchverified": MagicMock(from_cli_args=lambda args: fake_tasks)}):
        main(BASE_ARGS + ["--task", "swebenchverified"])

    assert mock_run_train_eval_loop.call_count == 2
