"""Focused tests for the read-only training runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.MicroBot import BotRunResult
from microbots.auto_memory.training.runner import LearningRunner

pytestmark = pytest.mark.unit


def test_learning_runner_constructs_and_invokes_reading_bot() -> None:
    bot = MagicMock()
    bot.run.return_value = BotRunResult(status=True, result="learned", error=None)

    with (
        patch("microbots.auto_memory.training.runner.MemoryTool") as memory_tool,
        patch(
            "microbots.auto_memory.training.runner.ReadingBot",
            return_value=bot,
        ) as reading_bot,
    ):
        result = LearningRunner(
            model="azure-openai/gpt-4o",
            source_path=Path("/source"),
            memory_dir=Path("/memory"),
            max_bot_steps=7,
        ).run("study this", timeout_s=30)

    memory_tool.assert_called_once_with(memory_dir="/memory")
    reading_bot.assert_called_once_with(
        model="azure-openai/gpt-4o",
        folder_to_mount="/source",
        additional_tools=[memory_tool.return_value],
    )
    bot.run.assert_called_once_with(
        "study this", max_iterations=7, timeout_in_seconds=30
    )
    assert result.status == "passed"
    assert result.output == "learned"
    assert result.error is None


@pytest.mark.parametrize(
    ("bot_result", "expected_status", "expected_error"),
    [
        (
            BotRunResult(False, None, "Timeout of 30 seconds"),
            "timeout",
            "Timeout of 30 seconds",
        ),
        (BotRunResult(False, None, "failed"), "error", "failed"),
        (BotRunResult(False, None, None), "error", "Unknown error"),
    ],
)
def test_learning_runner_maps_failures(
    bot_result: BotRunResult,
    expected_status: str,
    expected_error: str,
) -> None:
    with (
        patch("microbots.auto_memory.training.runner.MemoryTool"),
        patch("microbots.auto_memory.training.runner.ReadingBot") as reading_bot,
    ):
        reading_bot.return_value.run.return_value = bot_result
        result = LearningRunner(
            model="azure-openai/gpt-4o",
            source_path=Path("/source"),
            memory_dir=Path("/memory"),
        ).run("study this", timeout_s=30)

    assert result.status == expected_status
    assert result.output is None
    assert result.error == expected_error