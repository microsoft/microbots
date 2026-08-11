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
from enum import StrEnum
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.data_models import IterationStatus
from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.loop import StepOutcome, StopReason, run_bounded_loop
from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.runner import (
    LearningRunner,
    TrainingIterationResult,
)

logger = getLogger(__name__)


class TrainingFinalStatus(StrEnum):
    """Overall status of a completed training run."""

    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"


# Maps the generic loop's stop reason onto this loop's own TrainingFinalStatus.
_STOP_REASON_TO_FINAL_STATUS: dict[StopReason, TrainingFinalStatus] = {
    StopReason.LIMIT_REACHED: TrainingFinalStatus.COMPLETED,
    StopReason.TOTAL_TIMEOUT: TrainingFinalStatus.TIMEOUT,
    StopReason.ITERATION_TIMEOUT: TrainingFinalStatus.TIMEOUT,
    StopReason.ERROR: TrainingFinalStatus.ERROR,
}


@dataclass
class TrainingIterationRecord:
    """Per-iteration record persisted to ``training_run.jsonl``."""

    idx: int
    status: IterationStatus
    elapsed_s: float
    error: str | None = None


@dataclass
class TrainingSummary:
    """Summary of one completed training run."""

    final_status: TrainingFinalStatus
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
        last_iter_started = 0.0

        def step(idx: int) -> StepOutcome[TrainingIterationRecord]:
            """Run one training iteration and log its outcome.

            Parameters
            ----------
            idx : int
                Zero-based index of the iteration to run.

            Returns
            -------
            StepOutcome[TrainingIterationRecord]
                The iteration's record plus a stop signal when the runner
                itself reports a per-iteration timeout.
            """
            nonlocal last_iter_started
            prompt = agents_md + _ITER_HEADER.format(
                idx=idx, total=total, source=resolved_source
            )
            logger.info(
                "TrainingOrchestrator: iteration %d/%d starting", idx + 1, total
            )
            last_iter_started = time.monotonic()
            result: TrainingIterationResult = runner.run(
                prompt, timeout_s=self._config.per_iteration_timeout
            )
            iter_elapsed = time.monotonic() - last_iter_started
            record = TrainingIterationRecord(
                idx=idx,
                status=result.status,
                elapsed_s=iter_elapsed,
                error=result.error,
            )
            self._append_log(record)
            logger.info(
                "TrainingOrchestrator: iteration %d finished status=%s in %.1fs",
                idx,
                result.status,
                iter_elapsed,
            )
            stop = (
                StopReason.ITERATION_TIMEOUT
                if result.status == IterationStatus.TIMEOUT
                else None
            )
            return StepOutcome(record=record, stop=stop)

        def on_exception(idx: int, exc: BaseException) -> TrainingIterationRecord:
            """Build the final iteration record when the runner raises.

            Parameters
            ----------
            idx : int
                Zero-based index of the iteration that raised.
            exc : BaseException
                The caught exception instance.

            Returns
            -------
            TrainingIterationRecord
                An ``ERROR`` record carrying the exception type and message.
            """
            record = TrainingIterationRecord(
                idx=idx,
                status=IterationStatus.ERROR,
                elapsed_s=time.monotonic() - last_iter_started,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._append_log(record)
            logger.exception(
                "TrainingOrchestrator: iteration %d raised %s", idx, type(exc).__name__
            )
            return record

        result = run_bounded_loop(
            max_iterations=total,
            total_timeout_s=self._config.total_timeout_min * 60,
            step=step,
            catch_exceptions=(Exception,),
            on_exception=on_exception,
        )

        final_status = _STOP_REASON_TO_FINAL_STATUS[result.stop_reason]

        # Prefer the last record's own error (richer / iteration-scoped)
        # over the loop's generic error_message when both are available.
        error_message = (
            result.records[-1].error if result.records else result.error_message
        )
        if error_message is None:
            error_message = result.error_message

        return self._finish(
            final_status, result.records, result.elapsed_s, error=error_message
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
        final_status: TrainingFinalStatus,
        records: list[TrainingIterationRecord],
        elapsed_s: float,
        error: str | None,
    ) -> TrainingSummary:
        """Build and log the final training summary.

        Parameters
        ----------
        final_status : TrainingFinalStatus
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