"""Training orchestrator for learning agents.

Drives a sequence of :class:`~microbots.auto_memory.training.runner.LearningRunner`
iterations against a target source directory, accumulating notes in the
shared ``memory_dir``. Each iteration receives the same base ``AGENTS.md``
prompt plus a small header identifying the iteration index, the source
path, and the memory root - the agent uses the ``memory`` tool to read
prior notes and extend them.

The framework is deliberately domain-agnostic: what the agent is learning
is defined by the ``AGENTS.md`` file, and the source directory can hold
anything (a source-code repo, a docs tree, a dataset, an example gallery,
...).

There is deliberately **no** callback / feedback loop here (unlike the
eval loop in :mod:`microbots.auto_memory.orchestrator`). The only
persistent state that matters is the ``/memories/`` tree.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.runner import (
    LearningRunner,
    TrainingIterationResult,
)

logger = getLogger(__name__)


@dataclass
class TrainingIterationRecord:
    """Per-iteration record persisted to ``training_run.jsonl``."""

    idx: int
    status: str
    elapsed_s: float
    error: str | None = None


@dataclass
class TrainingSummary:
    """Summary of one completed training run."""

    final_status: str  # "completed" | "timeout" | "error"
    iterations_run: int
    iteration_records: list[TrainingIterationRecord] = field(default_factory=list)
    elapsed_s: float = 0.0
    memory_dir: Path | None = None
    error_message: str | None = None


_ITER_HEADER = (
    "\n\n---\n"
    "# Runtime Context\n"
    "- Iteration index (zero-based): {idx}\n"
    "- Total iterations planned: {total}\n"
    "- Source directory (mounted in sandbox): {source}\n"
    "- Memory root: /memories/\n"
)


class TrainingOrchestrator:
    """Repeatedly invoke the runner, accumulating notes in ``memory_dir``.

    Parameters
    ----------
    config : TrainingConfig
        Fully validated training configuration.
    workdir : Path
        Directory that receives ``training_meta.json`` and
        ``training_run.jsonl``. Created if missing.
    """

    def __init__(self, config: TrainingConfig, workdir: Path) -> None:
        """Initialize a training orchestrator.

        Parameters
        ----------
        config : TrainingConfig
            Fully validated training configuration.
        workdir : Path
            Directory for training metadata and logs.
        """
        self._config = config
        self._workdir = workdir
        self._meta_path = workdir / "training_meta.json"
        self._log_path = workdir / "training_run.jsonl"

    def run(self) -> TrainingSummary:
        """Execute all configured training iterations.

        Returns
        -------
        TrainingSummary
            Summary of the completed, timed out, or failed run.
        """
        self._prepare_workdir()
        self._prepare_memory_dir()

        resolved_source = self._config.source.materialize(
            default_dest=self._workdir / "source"
        )
        self._write_meta(resolved_source=resolved_source)

        runner = LearningRunner(
            model=self._config.model,
            source_path=resolved_source,
            memory_dir=self._config.memory_dir,
            max_bot_steps=self._config.max_bot_steps,
        )

        agents_md = self._config.read_agents_md()
        total = self._config.iterations
        total_budget_s = self._config.total_timeout_min * 60
        started = time.monotonic()
        records: list[TrainingIterationRecord] = []

        for idx in range(total):
            elapsed = time.monotonic() - started
            if total_budget_s and elapsed >= total_budget_s:
                logger.info(
                    "TrainingOrchestrator: total timeout reached after %.1fs (limit %ds)",
                    elapsed,
                    total_budget_s,
                )
                return self._finish("timeout", records, elapsed, error=None)

            prompt = agents_md + _ITER_HEADER.format(
                idx=idx,
                total=total,
                source=resolved_source,
            )

            logger.info(
                "TrainingOrchestrator: iteration %d/%d starting", idx + 1, total
            )
            iter_started = time.monotonic()
            try:
                result: TrainingIterationResult = runner.run(
                    prompt, timeout_s=self._config.per_iteration_timeout
                )
            except Exception as exc:  # noqa: BLE001 - surface as ERROR record
                iter_elapsed = time.monotonic() - iter_started
                record = TrainingIterationRecord(
                    idx=idx,
                    status="error",
                    elapsed_s=iter_elapsed,
                    error=f"{type(exc).__name__}: {exc}",
                )
                records.append(record)
                self._append_log(record)
                logger.exception(
                    "TrainingOrchestrator: iteration %d raised %s",
                    idx,
                    type(exc).__name__,
                )
                return self._finish(
                    "error",
                    records,
                    time.monotonic() - started,
                    error=record.error,
                )

            iter_elapsed = time.monotonic() - iter_started
            record = TrainingIterationRecord(
                idx=idx,
                status=result.status,
                elapsed_s=iter_elapsed,
                error=result.error,
            )
            records.append(record)
            self._append_log(record)

            logger.info(
                "TrainingOrchestrator: iteration %d finished status=%s in %.1fs",
                idx,
                result.status,
                iter_elapsed,
            )

            if result.status == "timeout":
                return self._finish(
                    "timeout",
                    records,
                    time.monotonic() - started,
                    error=result.error,
                )

        return self._finish(
            "completed",
            records,
            time.monotonic() - started,
            error=None,
        )

    def _prepare_workdir(self) -> None:
        """Create the training work directory if it does not exist."""
        try:
            self._workdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(
                f"Cannot create workdir {self._workdir}: {exc}"
            ) from exc

    def _prepare_memory_dir(self) -> None:
        """Create, or reset and recreate, the persistent memory directory."""
        mem = self._config.memory_dir
        if self._config.reset_memory and mem.exists():
            logger.info("TrainingOrchestrator: reset_memory=True - wiping %s", mem)
            shutil.rmtree(mem, ignore_errors=True)
        try:
            mem.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(
                f"Cannot create memory_dir {mem}: {exc}"
            ) from exc

    def _write_meta(self, *, resolved_source: Path) -> None:
        """Initialize run metadata and the iteration log.

        Parameters
        ----------
        resolved_source : Path
            Materialized local source directory used by the runner.
        """
        meta = {
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
            "source": self._config.source.to_meta(),
            "source_path": str(resolved_source),
            "memory_dir": str(self._config.memory_dir),
            "agents_md_path": str(self._config.agents_md_path),
            "model": self._config.model,
            "iterations": self._config.iterations,
            "per_iteration_timeout": self._config.per_iteration_timeout,
            "total_timeout_min": self._config.total_timeout_min,
            "max_bot_steps": self._config.max_bot_steps,
            "reset_memory": self._config.reset_memory,
        }
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._log_path.write_text("", encoding="utf-8")

    def _append_log(self, record: TrainingIterationRecord) -> None:
        """Append an iteration record to the JSON Lines log.

        Parameters
        ----------
        record : TrainingIterationRecord
            Completed iteration record to persist.
        """
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record)) + "\n")

    def _finish(
        self,
        final_status: str,
        records: list[TrainingIterationRecord],
        elapsed_s: float,
        error: str | None,
    ) -> TrainingSummary:
        """Build and log the final training summary.

        Parameters
        ----------
        final_status : str
            Overall completion status.
        records : list[TrainingIterationRecord]
            Iteration records accumulated during the run.
        elapsed_s : float
            Total elapsed wall-clock time in seconds.
        error : str | None
            Final error description, if any.

        Returns
        -------
        TrainingSummary
            Final summary for the run.
        """
        summary = TrainingSummary(
            final_status=final_status,
            iterations_run=len(records),
            iteration_records=records,
            elapsed_s=elapsed_s,
            memory_dir=self._config.memory_dir,
            error_message=error,
        )
        logger.info(
            "TrainingOrchestrator: finished status=%s iterations=%d elapsed=%.1fs",
            final_status,
            len(records),
            elapsed_s,
        )
        return summary