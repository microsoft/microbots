"""Unit tests for microbots.auto_memory.training.cli."""

import sys
from unittest.mock import patch

import pytest

from microbots.auto_memory.training.cli import main, parse_args
from microbots.MicroBot import BotRunResult


@pytest.mark.unit
def test_parse_args_defaults():
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--model",
        "azure-openai/gpt-4o",
    ]
    with patch.object(sys, "argv", argv):
        args = parse_args()

    assert args.repo == "/some/repo"
    assert args.model == "azure-openai/gpt-4o"
    assert args.feedback == ""
    assert args.memory_dir == "./memory"


@pytest.mark.unit
def test_main_calls_run_training_with_parsed_args():
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--feedback",
        "some feedback",
        "--memory-dir",
        "/some/memory",
        "--model",
        "azure-openai/gpt-4o",
    ]
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training",
        return_value=fake_result,
    ) as mock_run_training:
        main()

    mock_run_training.assert_called_once_with(
        repo_path="/some/repo",
        feedback="some feedback",
        memory_dir="/some/memory",
        model="azure-openai/gpt-4o",
    )


@pytest.mark.unit
def test_main_runs_multiple_iterations_with_same_memory_dir():
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--memory-dir",
        "/some/memory",
        "--model",
        "azure-openai/gpt-4o",
        "--iterations",
        "3",
    ]
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training",
        return_value=fake_result,
    ) as mock_run_training:
        main()

    assert mock_run_training.call_count == 3
    for call in mock_run_training.call_args_list:
        assert call.kwargs["memory_dir"] == "/some/memory"


@pytest.mark.unit
def test_main_logs_status_and_error_on_failure(caplog):
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--model",
        "azure-openai/gpt-4o",
    ]
    fake_result = BotRunResult(status=False, result=None, error="boom")

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training",
        return_value=fake_result,
    ), caplog.at_level("INFO", logger="microbots.auto_memory.training.cli"):
        main()

    assert "status=False" in caplog.text
    assert "error=boom" in caplog.text
