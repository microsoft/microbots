"""Tests for WritingBotRunner."""

import pytest
from unittest.mock import MagicMock, patch

from microbots.auto_memory.data_models import IterationStatus
from microbots.auto_memory.runners import AgentResult, IterationContext
from microbots.auto_memory.runners.writing_bot_runner import WritingBotRunner
from microbots.MicroBot import BotRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL = "azure/gpt-4o"
_TASK = "Write a summary to /memories/summary.md"


def _make_ctx(memory_dir: str, task: str = _TASK) -> IterationContext:
    return IterationContext(task=task, memory_dir=memory_dir)


# ---------------------------------------------------------------------------
# WritingBot construction contract
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWritingBotRunnerConstruction:
    """WritingBot must be created with the correct arguments from ctx."""

    def test_passes_memory_dir_as_folder_to_mount(self, tmp_path):
        ctx = _make_ctx(memory_dir=str(tmp_path))
        bot_mock = MagicMock()
        bot_mock.run.return_value = BotRunResult(status=True, result="done", error=None)

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ) as MockWritingBot:
            runner = WritingBotRunner(model=_MODEL)
            runner.run(ctx, timeout_s=60)

            MockWritingBot.assert_called_once()
            _, kwargs = MockWritingBot.call_args
            assert kwargs["folder_to_mount"] == ctx.memory_dir

    def test_passes_memory_tool_with_memory_dir(self, tmp_path):
        ctx = _make_ctx(memory_dir=str(tmp_path))
        bot_mock = MagicMock()
        bot_mock.run.return_value = BotRunResult(status=True, result="done", error=None)

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ) as MockWritingBot:
            with patch(
                "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
            ) as MockMemoryTool:
                memory_tool_instance = MagicMock()
                MockMemoryTool.return_value = memory_tool_instance

                runner = WritingBotRunner(model=_MODEL)
                runner.run(ctx, timeout_s=60)

                MockMemoryTool.assert_called_once_with(memory_dir=ctx.memory_dir)
                _, kwargs = MockWritingBot.call_args
                assert kwargs["additional_tools"] == [memory_tool_instance]

    def test_passes_model_to_writing_bot(self, tmp_path):
        ctx = _make_ctx(memory_dir=str(tmp_path))
        bot_mock = MagicMock()
        bot_mock.run.return_value = BotRunResult(status=True, result="done", error=None)

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ) as MockWritingBot:
            runner = WritingBotRunner(model=_MODEL)
            runner.run(ctx, timeout_s=60)

            _, kwargs = MockWritingBot.call_args
            assert kwargs["model"] == _MODEL

    def test_calls_bot_run_with_task_and_timeout(self, tmp_path):
        ctx = _make_ctx(memory_dir=str(tmp_path))
        bot_mock = MagicMock()
        bot_mock.run.return_value = BotRunResult(status=True, result="done", error=None)

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ):
            runner = WritingBotRunner(model=_MODEL)
            runner.run(ctx, timeout_s=120)

            bot_mock.run.assert_called_once_with(
                ctx.task, max_iterations=20, timeout_in_seconds=120
            )

    def test_custom_max_iterations_forwarded_to_bot(self, tmp_path):
        ctx = _make_ctx(memory_dir=str(tmp_path))
        bot_mock = MagicMock()
        bot_mock.run.return_value = BotRunResult(status=True, result="done", error=None)

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ):
            runner = WritingBotRunner(model=_MODEL, max_iterations=5)
            runner.run(ctx, timeout_s=60)

            bot_mock.run.assert_called_once_with(
                ctx.task, max_iterations=5, timeout_in_seconds=60
            )


# ---------------------------------------------------------------------------
# BotRunResult → AgentResult state mapping
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWritingBotRunnerResultMapping:
    """All three BotRunResult states must map to the correct AgentResult."""

    @pytest.fixture(autouse=True)
    def _set_memory_dir(self, tmp_path):
        self._memory_dir = str(tmp_path)

    def _run_with_bot_result(self, bot_result: BotRunResult) -> AgentResult:
        ctx = _make_ctx(memory_dir=self._memory_dir)
        bot_mock = MagicMock()
        bot_mock.run.return_value = bot_result

        with patch(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
            return_value=bot_mock,
        ):
            runner = WritingBotRunner(model=_MODEL)
            return runner.run(ctx, timeout_s=60)

    # --- success ---

    def test_success_maps_to_passed(self):
        result = self._run_with_bot_result(
            BotRunResult(status=True, result="Task completed", error=None)
        )
        assert result.status == IterationStatus.PASSED

    def test_success_carries_bot_output(self):
        result = self._run_with_bot_result(
            BotRunResult(status=True, result="Final answer", error=None)
        )
        assert result.output == "Final answer"

    def test_success_has_no_error(self):
        result = self._run_with_bot_result(
            BotRunResult(status=True, result="ok", error=None)
        )
        assert result.error is None

    # --- timeout ---

    def test_timeout_maps_to_timeout_status(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error="Timeout of 60 seconds reached")
        )
        assert result.status == IterationStatus.TIMEOUT

    def test_timeout_carries_error_message(self):
        error_msg = "Timeout of 60 seconds reached"
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error=error_msg)
        )
        assert result.error == error_msg

    def test_timeout_has_no_output(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error="Timeout of 60 seconds reached")
        )
        assert result.output is None

    # --- generic error (e.g. max iterations reached) ---

    def test_max_iterations_maps_to_error_status(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error="Max iterations 20 reached")
        )
        assert result.status == IterationStatus.ERROR

    def test_generic_error_maps_to_error_status(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error="Did not complete")
        )
        assert result.status == IterationStatus.ERROR

    def test_generic_error_carries_error_message(self):
        error_msg = "Max iterations 20 reached"
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error=error_msg)
        )
        assert result.error == error_msg

    def test_generic_error_has_no_output(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error="Max iterations 20 reached")
        )
        assert result.output is None

    def test_none_error_on_failure_maps_to_error_status(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error=None)
        )
        assert result.status == IterationStatus.ERROR

    def test_none_error_on_failure_uses_fallback_message(self):
        result = self._run_with_bot_result(
            BotRunResult(status=False, result=None, error=None)
        )
        assert result.error == "Unknown error"
