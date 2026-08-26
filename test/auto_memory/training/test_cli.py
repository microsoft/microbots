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
    assert args.iterations == 1


@pytest.mark.unit
def test_main_calls_run_training_loop_with_parsed_args():
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
        "--iterations",
        "3",
    ]
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training_loop",
        return_value=fake_result,
    ) as mock_run_training_loop:
        main()

    mock_run_training_loop.assert_called_once_with(
        repo_path="/some/repo",
        feedback="some feedback",
        memory_dir="/some/memory",
        model="azure-openai/gpt-4o",
        iterations=3,
    )


@pytest.mark.unit
def test_main_logs_error_when_loop_fails_on_last_iteration(caplog):
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--model",
        "azure-openai/gpt-4o",
    ]
    fake_result = BotRunResult(status=False, result=None, error="boom")

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training_loop",
        return_value=fake_result,
    ), caplog.at_level("ERROR", logger="microbots.auto_memory.training.cli"):
        main()

    assert "boom" in caplog.text


@pytest.mark.unit
def test_main_does_not_log_error_when_loop_succeeds(caplog):
    argv = [
        "cli.py",
        "--repo",
        "/some/repo",
        "--model",
        "azure-openai/gpt-4o",
    ]
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch.object(sys, "argv", argv), patch(
        "microbots.auto_memory.training.cli.run_training_loop",
        return_value=fake_result,
    ), caplog.at_level("ERROR", logger="microbots.auto_memory.training.cli"):
        main()

    assert caplog.text == ""
