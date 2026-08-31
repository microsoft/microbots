"""Unit tests for microbots.auto_memory.training.runner.

All external dependencies (ReadingBot, MemoryTool) are mocked so these
tests run without Docker, network access, or an LLM.

runner.py no longer manages repo cloning or looping: repo_path is
always assumed to be a ready local directory prepared by the caller
(e.g. the orchestrator or an EvalTask's setup), and iterating training
passes is the orchestrator's responsibility.
"""

from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory.training.runner import run_training
from microbots.MicroBot import BotRunResult


# ---------------------------------------------------------------------------
# run_training
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_training_prompt_includes_feedback(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="Focus on error handling paths.",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    prompt_arg = mock_bot_instance.run.call_args.args[0]
    assert "Focus on error handling paths." in prompt_arg


@pytest.mark.unit
def test_run_training_prompt_handles_empty_feedback(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    prompt_arg = mock_bot_instance.run.call_args.args[0]
    assert "No feedback provided for this run." in prompt_arg


@pytest.mark.unit
def test_run_training_passes_correct_args_to_reading_bot(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )
    mock_memory_tool_instance = MagicMock()

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ) as mock_reading_bot, patch(
        "microbots.auto_memory.training.runner.MemoryTool",
        return_value=mock_memory_tool_instance,
    ) as mock_memory_tool:
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    mock_memory_tool.assert_called_once_with(memory_dir=str(memory_dir))

    _, kwargs = mock_reading_bot.call_args
    assert kwargs["model"] == "azure-openai/gpt-4o"
    # repo_path is used directly as folder_to_mount now; no cloning/staging.
    assert kwargs["folder_to_mount"] == str(local_repo)
    assert kwargs["additional_tools"] == [mock_memory_tool_instance]


@pytest.mark.unit
def test_run_training_passes_max_iterations_and_timeout_to_bot_run(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
            max_iterations=5,
            timeout_in_seconds=42,
        )

    _, kwargs = mock_bot_instance.run.call_args
    assert kwargs["max_iterations"] == 5
    assert kwargs["timeout_in_seconds"] == 42


@pytest.mark.unit
def test_run_training_returns_bot_result(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    expected_result = BotRunResult(status=True, result="done", error=None)
    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = expected_result

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        result = run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    assert result is expected_result


@pytest.mark.unit
def test_run_training_does_not_modify_repo_path(tmp_path):
    """run_training must never delete/modify repo_path itself - it does
    not own the repo's lifecycle anymore (no cloning, no cleanup)."""
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    (local_repo / "marker.txt").write_text("keep me")
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    assert (local_repo / "marker.txt").exists()
