"""End-to-end tests for the auto_memory CLI entry point."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory import run_from_yaml
from microbots.auto_memory.data_models import FinalStatus
from microbots.auto_memory.orchestrator import RunSummary
from microbots.MicroBot import BotRunResult

_MODEL = "azure/gpt-4o"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_YAML = textwrap.dedent("""\
    task_definition: Write a hello message to /memories/hello.txt
    prompt_template: "Goal: {{ task }}"
    callbacks:
      - name: always_ok
        command: 'true'
    max_iterations: 1
    timeout_min: 1
    per_iteration_timeout: 30
""")

_TASK_YAML_FAILING = textwrap.dedent("""\
    task_definition: Write a hello message to /memories/hello.txt
    prompt_template: "Goal: {{ task }}"
    callbacks:
      - name: always_fail
        command: 'false'
    max_iterations: 2
    timeout_min: 1
    per_iteration_timeout: 30
""")


def _write_yaml(tmp_path: Path, content: str = _TASK_YAML) -> Path:
    p = tmp_path / "task.yml"
    p.write_text(content)
    return p


def _mock_writing_bot(status: bool = True, error: str | None = None):
    """Patch WritingBot to return a controllable BotRunResult."""
    bot_instance = MagicMock()
    bot_instance.run.return_value = BotRunResult(
        status=status,
        result="agent output" if status else None,
        error=error,
    )
    return patch(
        "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
        return_value=bot_instance,
    ), bot_instance


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunFromYamlEndToEnd:
    def test_returns_run_summary(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="t1", model=_MODEL
            )

        assert isinstance(summary, RunSummary)

    def test_final_status_passed_when_callbacks_pass(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="t2", model=_MODEL
            )

        assert summary.final_status == FinalStatus.PASSED
        assert summary.iterations_run == 1
        assert summary.error_message is None
        assert len(summary.iteration_records) == 1

    def test_disk_layout_created(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            run_from_yaml(
                str(yaml_path), str(workdir), run_id="layout_run", model=_MODEL
            )

        run_dir = workdir / "runs" / "layout_run"
        assert run_dir.is_dir()
        assert (run_dir / "run_meta.json").is_file()
        assert (run_dir / "memory").is_dir()
        assert (run_dir / "memory" / "feedback.jsonl").is_file()
        assert (run_dir / "iterations" / "iter_00").is_dir()
        assert (run_dir / "iterations" / "iter_00" / "candidate").is_dir()
        assert (run_dir / "iterations" / "iter_00" / "logs").is_dir()

    def test_writing_bot_receives_memory_dir(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, bot_instance = _mock_writing_bot()

        with bot_patch as MockBot, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ) as MockMemoryTool:
            run_from_yaml(
                str(yaml_path), str(workdir), run_id="mem_run", model=_MODEL
            )

        expected_memory_dir = str(workdir / "runs" / "mem_run" / "memory")
        _, kwargs = MockBot.call_args
        assert kwargs["folder_to_mount"] == expected_memory_dir
        MockMemoryTool.assert_called_once_with(memory_dir=expected_memory_dir)

    def test_auto_generated_run_id(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(str(yaml_path), str(workdir), model=_MODEL)

        assert summary.final_status == FinalStatus.PASSED
        runs_dir = workdir / "runs"
        children = [p for p in runs_dir.iterdir() if p.is_dir()]
        assert len(children) == 1
        assert children[0].name.startswith("run-")

    def test_failing_callbacks_persist_feedback_and_reach_limit(self, tmp_path):
        yaml_path = _write_yaml(tmp_path, _TASK_YAML_FAILING)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="fail_run", model=_MODEL
            )

        assert summary.final_status == FinalStatus.LIMIT_REACHED
        assert summary.iterations_run == 2

        run_dir = workdir / "runs" / "fail_run"
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        assert feedback_file.is_file()
        lines = [ln for ln in feedback_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2
        assert (run_dir / "iterations" / "iter_01" / "candidate").is_dir()
