"""Unit tests for microbots.auto_memory.cli."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.cli import main, parse_args

MODULE = "microbots.auto_memory.cli"

BASE_ARGS = ["--model", "azure-openai/gpt-4o"]
FAKE_WORKDIR = Path("/workdir")


@pytest.mark.unit
def test_parse_args_defaults():
    args = parse_args(BASE_ARGS)

    assert args.model == "azure-openai/gpt-4o"
    assert args.task is None
    assert args.max_rounds == 5
    assert args.training_iterations == 10


@pytest.mark.unit
def test_parse_args_accepts_known_task():
    args = parse_args(BASE_ARGS + ["--task", "swebenchverified"])

    assert args.task == "swebenchverified"


@pytest.mark.unit
def test_parse_args_rejects_unknown_task():
    with pytest.raises(SystemExit):
        parse_args(BASE_ARGS + ["--task", "does-not-exist"])


@pytest.mark.unit
def test_parse_args_workdir_defaults_to_none():
    args = parse_args(BASE_ARGS)

    assert args.workdir is None


@pytest.mark.unit
def test_parse_args_picks_up_explicit_workdir():
    args = parse_args(BASE_ARGS + ["--workdir", "/custom/workdir"])

    assert args.workdir == "/custom/workdir"


@pytest.mark.unit
@patch(f"{MODULE}.require_workdir")
@patch(f"{MODULE}.resolve_workdir")
@patch(f"{MODULE}.load_config", return_value={})
@patch(f"{MODULE}.run")
def test_main_uses_explicit_workdir_over_resolve_workdir(
    mock_run, mock_load_config, mock_resolve_workdir, mock_require_workdir
):
    main(BASE_ARGS + ["--workdir", "/custom/workdir"])

    mock_resolve_workdir.assert_not_called()
    mock_require_workdir.assert_called_once_with(Path("/custom/workdir"))
    mock_run.assert_called_once_with(
        workdir=Path("/custom/workdir"),
        model="azure-openai/gpt-4o",
        task=None,
        max_rounds=5,
        training_iterations=10,
        config={},
    )


@pytest.mark.unit
@patch(f"{MODULE}.require_workdir")
@patch(f"{MODULE}.resolve_workdir", return_value=FAKE_WORKDIR)
@patch(f"{MODULE}.load_config", return_value={})
@patch(f"{MODULE}.run")
def test_main_falls_back_to_resolve_workdir_when_not_given(
    mock_run, mock_load_config, mock_resolve_workdir, mock_require_workdir
):
    main(BASE_ARGS)

    mock_resolve_workdir.assert_called_once_with()
    mock_require_workdir.assert_called_once_with(FAKE_WORKDIR)
    mock_run.assert_called_once_with(
        workdir=FAKE_WORKDIR,
        model="azure-openai/gpt-4o",
        task=None,
        max_rounds=5,
        training_iterations=10,
        config={},
    )


@pytest.mark.unit
@patch(f"{MODULE}.require_workdir")
@patch(f"{MODULE}.resolve_workdir", return_value=FAKE_WORKDIR)
@patch(f"{MODULE}.run")
def test_main_calls_run_with_task_none_when_task_omitted(mock_run, mock_resolve_workdir, mock_require_workdir):
    main(BASE_ARGS)

    assert mock_run.call_args.kwargs["task"] is None


@pytest.mark.unit
@patch(f"{MODULE}.require_workdir")
@patch(f"{MODULE}.resolve_workdir", return_value=FAKE_WORKDIR)
@patch(f"{MODULE}.load_config", return_value={})
@patch(f"{MODULE}.run")
def test_main_calls_run_for_each_task_when_task_given(
    mock_run, mock_load_config, mock_resolve_workdir, mock_require_workdir
):
    fake_task = MagicMock()
    mock_run.return_value = MagicMock(passed=True, rounds_run=1)

    with patch(f"{MODULE}.TASK_REGISTRY", {"swebenchverified": MagicMock(from_config=lambda task_args: [fake_task])}):
        main(BASE_ARGS + ["--task", "swebenchverified"])

    mock_run.assert_called_once_with(
        workdir=FAKE_WORKDIR,
        model="azure-openai/gpt-4o",
        task=fake_task,
        max_rounds=5,
        training_iterations=10,
        config={},
    )


@pytest.mark.unit
@patch(f"{MODULE}.require_workdir")
@patch(f"{MODULE}.resolve_workdir", return_value=FAKE_WORKDIR)
@patch(f"{MODULE}.load_config", return_value={})
@patch(f"{MODULE}.run")
def test_main_runs_once_per_returned_task(mock_run, mock_load_config, mock_resolve_workdir, mock_require_workdir):
    fake_tasks = [MagicMock(), MagicMock()]
    mock_run.return_value = MagicMock(passed=False, rounds_run=5)

    with patch(f"{MODULE}.TASK_REGISTRY", {"swebenchverified": MagicMock(from_config=lambda task_args: fake_tasks)}):
        main(BASE_ARGS + ["--task", "swebenchverified"])

    assert mock_run.call_count == 2
