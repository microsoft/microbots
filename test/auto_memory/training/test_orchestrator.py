"""Focused tests for TrainingOrchestrator."""

from pathlib import Path
from unittest.mock import patch

import pytest

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training import TrainingOrchestrator
from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.orchestrator import (
    TrainingOrchestrator as DirectOrchestrator,
)
from microbots.auto_memory.training.runner import TrainingIterationResult
from microbots.auto_memory.training.training_source import TrainingSource


def _config(tmp_path: Path, *, iterations: int = 2) -> TrainingConfig:
    source = tmp_path / "source"
    source.mkdir()
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("Learn the repository.", encoding="utf-8")
    return TrainingConfig(
        source=TrainingSource(type="path", path=source),
        memory_dir=tmp_path / "memory",
        model="azure-openai/gpt-4o",
        agents_md_path=agents_md,
        iterations=iterations,
        per_iteration_timeout=45,
        max_bot_steps=9,
    )


def test_public_export_is_renamed_orchestrator() -> None:
    assert TrainingOrchestrator is DirectOrchestrator


def test_completed_run_records_iterations_and_runtime_context(tmp_path: Path) -> None:
    config = _config(tmp_path)
    passed = TrainingIterationResult("passed", "done", None)

    with patch(
        "microbots.auto_memory.training.orchestrator.LearningRunner"
    ) as runner_class:
        runner_class.return_value.run.return_value = passed
        summary = TrainingOrchestrator(config, tmp_path / "work").run()

    runner_class.assert_called_once_with(
        model=config.model,
        source_path=config.source.path,
        memory_dir=config.memory_dir,
        max_bot_steps=config.max_bot_steps,
    )
    assert summary.final_status == "completed"
    assert summary.iterations_run == 2
    assert [record.status for record in summary.iteration_records] == [
        "passed",
        "passed",
    ]
    first_prompt = runner_class.return_value.run.call_args_list[0].args[0]
    assert "Learn the repository." in first_prompt
    assert "Iteration index (zero-based): 0" in first_prompt
    assert f"Source directory (mounted in sandbox): {config.source.path}" in first_prompt
    assert runner_class.return_value.run.call_args_list[0].kwargs == {
        "timeout_s": 45
    }


def test_timeout_result_stops_the_run(tmp_path: Path) -> None:
    config = _config(tmp_path, iterations=3)
    timeout = TrainingIterationResult("timeout", None, "Timeout of 45 seconds")

    with patch(
        "microbots.auto_memory.training.orchestrator.LearningRunner"
    ) as runner_class:
        runner_class.return_value.run.return_value = timeout
        summary = TrainingOrchestrator(config, tmp_path / "work").run()

    assert summary.final_status == "timeout"
    assert summary.iterations_run == 1
    assert summary.error_message == "Timeout of 45 seconds"


def test_runner_exception_returns_error_summary(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with patch(
        "microbots.auto_memory.training.orchestrator.LearningRunner"
    ) as runner_class:
        runner_class.return_value.run.side_effect = RuntimeError("broken")
        summary = TrainingOrchestrator(config, tmp_path / "work").run()

    assert summary.final_status == "error"
    assert summary.iterations_run == 1
    assert summary.error_message == "RuntimeError: broken"


def test_total_timeout_stops_before_an_iteration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.total_timeout_min = 1

    with patch(
        "microbots.auto_memory.training.orchestrator.time.monotonic",
        side_effect=[0.0, 61.0],
    ):
        summary = TrainingOrchestrator(config, tmp_path / "work").run()

    assert summary.final_status == "timeout"
    assert summary.iterations_run == 0


def test_prepare_workdir_reports_creation_error(tmp_path: Path) -> None:
    orchestrator = TrainingOrchestrator(_config(tmp_path), tmp_path / "work")

    with (
        patch.object(Path, "mkdir", side_effect=OSError("denied")),
        pytest.raises(ConfigError, match="Cannot create workdir"),
    ):
        orchestrator.run()


def test_prepare_memory_resets_and_reports_creation_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.reset_memory = True
    config.memory_dir.mkdir()
    (config.memory_dir / "old").write_text("data", encoding="utf-8")
    orchestrator = TrainingOrchestrator(config, tmp_path / "work")

    orchestrator._prepare_memory_dir()
    assert config.memory_dir.exists()
    assert not (config.memory_dir / "old").exists()

    with (
        patch.object(Path, "mkdir", side_effect=OSError("denied")),
        pytest.raises(ConfigError, match="Cannot create memory_dir"),
    ):
        orchestrator._prepare_memory_dir()