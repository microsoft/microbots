"""Tests for programmatic and command-line training entry points."""

import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.cli import (
    main,
    run_training,
    run_training_from_yaml,
)
from microbots.auto_memory.training.orchestrator import TrainingSummary
from microbots.auto_memory.training.training_source import TrainingSource

pytestmark = pytest.mark.unit


def _summary(*, error: str | None = None) -> TrainingSummary:
    return TrainingSummary(
        final_status="completed",
        iterations_run=2,
        elapsed_s=1.25,
        memory_dir=Path("/memory"),
        error_message=error,
    )


def test_run_training_accepts_source_forms_and_default_workdir(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source"
    source_path.mkdir()
    agents = tmp_path / "AGENTS.md"
    agents.write_text("learn", encoding="utf-8")

    with patch(
        "microbots.auto_memory.training.cli.TrainingOrchestrator"
    ) as orchestrator:
        orchestrator.return_value.run.return_value = _summary()
        result = run_training(
            source={"type": "path", "path": source_path},
            memory_dir=tmp_path / "memory",
            model="azure-openai/gpt-4o",
            agents_md_path=agents,
        )

    assert result.final_status == "completed"
    config = orchestrator.call_args.kwargs["config"]
    assert config.source.path == source_path
    assert orchestrator.call_args.kwargs["workdir"].name.startswith(
        ".training-run-"
    )

    source = TrainingSource(type="path", path=source_path)
    with patch(
        "microbots.auto_memory.training.cli.TrainingOrchestrator"
    ) as orchestrator:
        orchestrator.return_value.run.return_value = _summary()
        run_training(
            source=source,
            memory_dir=tmp_path / "memory",
            model="azure-openai/gpt-4o",
            workdir=tmp_path / "work",
        )
    assert orchestrator.call_args.kwargs["config"].source is source
    assert orchestrator.call_args.kwargs["workdir"] == tmp_path / "work"

    with patch(
        "microbots.auto_memory.training.cli.TrainingOrchestrator"
    ) as orchestrator:
        orchestrator.return_value.run.return_value = _summary()
        run_training(
            source_path=source_path,
            memory_dir=tmp_path / "memory",
            model="azure-openai/gpt-4o",
            workdir=tmp_path / "work",
        )
    assert orchestrator.call_args.kwargs["config"].source.path == source_path


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "required"),
        (
            {"source": TrainingSource(), "source_path": "."},
            "either 'source' or 'source_path'",
        ),
        ({"source": object()}, "must be a TrainingSource or mapping"),
    ],
)
def test_run_training_rejects_invalid_source(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        run_training(
            **kwargs,
            memory_dir=tmp_path / "memory",
            model="azure-openai/gpt-4o",
        )


def test_run_training_from_yaml_uses_explicit_and_default_workdir(
    tmp_path: Path,
) -> None:
    config = MagicMock()
    config.memory_dir = tmp_path / "memory"
    with (
        patch(
            "microbots.auto_memory.training.cli.TrainingConfig.load_from_yaml",
            return_value=config,
        ),
        patch(
            "microbots.auto_memory.training.cli.TrainingOrchestrator"
        ) as orchestrator,
    ):
        orchestrator.return_value.run.return_value = _summary()
        run_training_from_yaml("config.yaml")
        assert orchestrator.call_args.kwargs["workdir"].name.startswith(
            ".training-run-"
        )
        run_training_from_yaml("config.yaml", workdir=tmp_path / "work")
        assert orchestrator.call_args.kwargs["workdir"] == tmp_path / "work"


def test_main_config_success_and_error_output(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "microbots.auto_memory.training.cli.run_training_from_yaml",
        return_value=_summary(error="last failure"),
    ) as run:
        assert main(["--config", "config.yaml", "--workdir", "work", "-v"]) == 0
    run.assert_called_once_with(Path("config.yaml"), workdir=Path("work"))
    captured = capsys.readouterr()
    assert "training completed" in captured.out
    assert "last error: last failure" in captured.err

    with patch(
        "microbots.auto_memory.training.cli.run_training_from_yaml",
        side_effect=ConfigError("bad config"),
    ):
        assert main(["--config", "bad.yaml"]) == 2
    assert "config error: bad config" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "missing"),
    [
        ([], "--memory, --model"),
        (["--memory", "memory"], "--model"),
        (["--model", "azure-openai/gpt-4o"], "--memory"),
    ],
)
def test_main_reports_missing_required_flags(
    args: list[str], missing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == 2
    assert missing in capsys.readouterr().err


def test_main_reports_missing_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--memory", "memory", "--model", "azure-openai/gpt-4o"]) == 2
    assert "--source or --source-git-url" in capsys.readouterr().err


def test_main_runs_local_and_git_sources(tmp_path: Path) -> None:
    with patch(
        "microbots.auto_memory.training.cli.run_training", return_value=_summary()
    ) as run:
        assert (
            main(
                [
                    "--source",
                    str(tmp_path),
                    "--memory",
                    "memory",
                    "--model",
                    "azure-openai/gpt-4o",
                ]
            )
            == 0
        )
    assert run.call_args.kwargs["source_path"] == tmp_path

    with patch(
        "microbots.auto_memory.training.cli.run_training", return_value=_summary()
    ) as run:
        assert (
            main(
                [
                    "--source-git-url",
                    "url",
                    "--source",
                    str(tmp_path / "checkout"),
                    "--source-cache-dir",
                    str(tmp_path / "cache"),
                    "--source-ref",
                    "main",
                    "--memory",
                    "memory",
                    "--model",
                    "azure-openai/gpt-4o",
                    "--iterations",
                    "2",
                    "--per-iteration-timeout",
                    "10",
                    "--total-timeout-min",
                    "3",
                    "--max-bot-steps",
                    "4",
                    "--reset-memory",
                    "--agents-md",
                    "AGENTS.md",
                ]
            )
            == 0
        )
    source = run.call_args.kwargs["source"]
    assert source.path == (tmp_path / "checkout").resolve()
    assert source.cache_dir == (tmp_path / "cache").resolve()
    assert source.ref == "main"

    with patch(
        "microbots.auto_memory.training.cli.run_training", return_value=_summary()
    ) as run:
        main(
            [
                "--source-git-url",
                "url",
                "--memory",
                "memory",
                "--model",
                "azure-openai/gpt-4o",
            ]
        )
    assert run.call_args.kwargs["source"].path is None
    assert run.call_args.kwargs["source"].cache_dir is None


def test_module_entry_point_exits_with_main_result() -> None:
    with (
        patch("microbots.auto_memory.training.cli.main", return_value=7),
        pytest.raises(SystemExit, match="7"),
    ):
        runpy.run_module("microbots.auto_memory.training.__main__", run_name="__main__")
