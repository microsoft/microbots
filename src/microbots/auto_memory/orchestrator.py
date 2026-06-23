"""TrainingLoopOrchestrator — wires all auto_memory components into a full iteration loop."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.analyzer import analyze_failure
from microbots.auto_memory.callbacks import CallbackResult, CallbackRunner
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.context import build_iteration_context
from microbots.auto_memory.data_models import Feedback, FinalStatus, IterationStatus
from microbots.auto_memory.errors import AgentError
from microbots.auto_memory.runners.base import AgentResult, AgentRunner, IterationContext
from microbots.auto_memory.workspace import WorkspaceManager

logger = getLogger(__name__)


# ---------------------------------------------------------------------------
# RunSummary
# ---------------------------------------------------------------------------


@dataclass
class IterationRecord:
    """Record of a single completed iteration."""

    idx: int
    status: IterationStatus
    feedback: Feedback | None = None


@dataclass
class RunSummary:
    """Summary of a completed auto_memory run.

    Attributes
    ----------
    final_status : FinalStatus
        Overall outcome of the run.
    iterations_run : int
        Total number of iterations executed.
    iteration_records : list[IterationRecord]
        Per-iteration outcomes and feedback.
    elapsed_s : float
        Total wall-clock time for the run in seconds.
    error_message : str | None
        Set when ``final_status`` is ``ERROR``; otherwise ``None``.
    """

    final_status: FinalStatus
    iterations_run: int
    iteration_records: list[IterationRecord] = field(default_factory=list)
    elapsed_s: float = 0.0
    error_message: str | None = None


# ---------------------------------------------------------------------------
# TrainingLoopOrchestrator
# ---------------------------------------------------------------------------


class TrainingLoopOrchestrator:
    """Wires all auto_memory components and drives the full iteration loop.

    Example usage::

        orchestrator = TrainingLoopOrchestrator(
            config=cfg,
            agent_runner=WritingBotRunner(model="azure/gpt-4o"),
            callback_runner=ShellCallbackRunner(),
            workspace=WorkspaceManager(run_dir=Path("runs/my_task")),
        )
        summary = orchestrator.run()

    Parameters
    ----------
    config : TaskConfig
        Task configuration (max_iterations, timeout_min, etc.).
    agent_runner : AgentRunner
        Structural-protocol object that executes one agent iteration.
    callback_runner : CallbackRunner
        Runs validation callbacks against the agent's output.
    workspace : WorkspaceManager
        Manages the on-disk layout for the run.
    max_agent_retries : int, optional
        Maximum number of consecutive transient agent ``ERROR`` results to
        tolerate before aborting the run.  Each retry consumes one iteration
        slot.  Defaults to ``2``.
    """

    def __init__(
        self,
        config: TaskConfig,
        agent_runner: AgentRunner,
        callback_runner: CallbackRunner,
        workspace: WorkspaceManager,
        max_agent_retries: int = 2,
    ) -> None:
        """Store injected collaborators used throughout the iteration loop.

        Parameters
        ----------
        config : TaskConfig
            Task configuration (max_iterations, timeout_min, etc.).
        agent_runner : AgentRunner
            Structural-protocol object that executes one agent iteration.
        callback_runner : CallbackRunner
            Runs validation callbacks against the agent's output.
        workspace : WorkspaceManager
            Manages the on-disk layout for the run.
        max_agent_retries : int, optional
            Maximum consecutive transient agent errors before aborting.
            Defaults to ``2``.
        """
        self._config = config
        self._agent_runner = agent_runner
        self._callback_runner = callback_runner
        self._workspace = workspace
        self._max_agent_retries = max_agent_retries

    # ------------------------------------------------------------------
    # Public API

    def run(self) -> RunSummary:
        """Execute the full iteration loop and return a :class:`RunSummary`.

        The loop terminates on one of four conditions: all callbacks pass
        (``PASSED``), ``max_iterations`` is exhausted without a pass
        (``LIMIT_REACHED``), total wall-clock time exceeds
        ``timeout_min * 60`` seconds (``TIMEOUT``), or the agent runner
        raises :class:`~microbots.auto_memory.errors.AgentError` or returns
        ``IterationStatus.ERROR`` more than ``max_agent_retries`` consecutive
        times (``ERROR``).

        Returns
        -------
        RunSummary
            Complete summary of the run including the final status and all
            per-iteration records.
        """
        self._workspace.prepare()

        start_time = time.monotonic()
        timeout_s = self._config.timeout_min * 60
        records: list[IterationRecord] = []
        last_feedback: Feedback | None = None
        consecutive_errors = 0

        for iteration_idx in range(self._config.max_iterations):
            elapsed = time.monotonic() - start_time

            # --- total timeout check ---
            if elapsed >= timeout_s:
                logger.info(
                    "Orchestrator: total timeout reached after %.1fs (limit %ds)",
                    elapsed,
                    timeout_s,
                )
                return RunSummary(
                    final_status=FinalStatus.TIMEOUT,
                    iterations_run=iteration_idx,
                    iteration_records=records,
                    elapsed_s=elapsed,
                )

            # --- run one iteration ---
            try:
                record = self.run_iteration(
                    iteration_idx=iteration_idx,
                    feedback=last_feedback,
                )
            except AgentError as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "Orchestrator: AgentError on iteration %d: %s", iteration_idx, exc
                )
                return RunSummary(
                    final_status=FinalStatus.ERROR,
                    iterations_run=iteration_idx,
                    iteration_records=records,
                    elapsed_s=elapsed,
                    error_message=str(exc),
                )

            records.append(record)

            if record.status == IterationStatus.ERROR:
                consecutive_errors += 1
                if consecutive_errors <= self._max_agent_retries:
                    logger.warning(
                        "Orchestrator: transient agent error on iteration %d "
                        "(retry %d/%d), continuing",
                        iteration_idx,
                        consecutive_errors,
                        self._max_agent_retries,
                    )
                    continue
                elapsed = time.monotonic() - start_time
                error_msg = (
                    record.feedback.summary
                    if record.feedback
                    else f"Agent returned ERROR on iteration {iteration_idx}"
                )
                logger.error(
                    "Orchestrator: iteration %d returned ERROR (%d consecutive)",
                    iteration_idx,
                    consecutive_errors,
                )
                return RunSummary(
                    final_status=FinalStatus.ERROR,
                    iterations_run=iteration_idx + 1,
                    iteration_records=records,
                    elapsed_s=elapsed,
                    error_message=error_msg,
                )

            consecutive_errors = 0

            if record.status == IterationStatus.TIMEOUT:
                elapsed = time.monotonic() - start_time
                logger.info(
                    "Orchestrator: per-iteration timeout on iteration %d", iteration_idx
                )
                return RunSummary(
                    final_status=FinalStatus.TIMEOUT,
                    iterations_run=iteration_idx + 1,
                    iteration_records=records,
                    elapsed_s=elapsed,
                )

            if record.status == IterationStatus.PASSED:
                elapsed = time.monotonic() - start_time
                logger.info(
                    "Orchestrator: PASSED on iteration %d (%.1fs)", iteration_idx, elapsed
                )
                return RunSummary(
                    final_status=FinalStatus.PASSED,
                    iterations_run=iteration_idx + 1,
                    iteration_records=records,
                    elapsed_s=elapsed,
                )

            # FAILED — persist feedback and continue
            last_feedback = record.feedback

        # All iterations exhausted without a pass
        elapsed = time.monotonic() - start_time
        logger.info(
            "Orchestrator: limit reached after %d iteration(s)", self._config.max_iterations
        )
        return RunSummary(
            final_status=FinalStatus.LIMIT_REACHED,
            iterations_run=self._config.max_iterations,
            iteration_records=records,
            elapsed_s=elapsed,
        )

    def run_iteration(
        self,
        iteration_idx: int,
        feedback: Feedback | None = None,
    ) -> IterationRecord:
        """Execute a single agent iteration and return an :class:`IterationRecord`.

        Prepares the workspace directory, builds the prompt, runs the agent,
        and — when the agent succeeds — runs callbacks. Returns ``PASSED`` if
        all callbacks pass; otherwise calls :meth:`analyze_failure`, persists
        the feedback, and returns ``FAILED``. Returns immediately on agent
        ``TIMEOUT`` or ``ERROR`` without invoking callbacks.

        Parameters
        ----------
        iteration_idx : int
            Zero-based index of the iteration.
        feedback : Feedback | None
            Feedback from the previous iteration, or ``None`` on the first.

        Returns
        -------
        IterationRecord
            Status and (when failed) structured feedback for this iteration.

        Raises
        ------
        AgentError
            Re-raised from the agent runner when the error is unrecoverable.
        """
        logger.debug("Orchestrator: starting iteration %d", iteration_idx)

        idir = self._workspace.prepare_iteration(iteration_idx)
        candidate_path = idir / self._config.output_path
        logs_dir = idir / "logs"
        memory_dir = str(self._workspace.memory.memory_dir)

        task_prompt = build_iteration_context(
            self._config,
            iteration_idx,
            feedback=feedback,
        )

        ctx = IterationContext(task=task_prompt, memory_dir=memory_dir)

        # Run agent
        agent_result: AgentResult = self._agent_runner.run(
            ctx, timeout_s=self._config.per_iteration_timeout
        )

        if agent_result.status == IterationStatus.TIMEOUT:
            logger.debug("Orchestrator: agent timed out on iteration %d", iteration_idx)
            return IterationRecord(idx=iteration_idx, status=IterationStatus.TIMEOUT)

        if agent_result.status == IterationStatus.ERROR:
            logger.debug(
                "Orchestrator: agent error on iteration %d: %s",
                iteration_idx,
                agent_result.error,
            )
            return IterationRecord(idx=iteration_idx, status=IterationStatus.ERROR)

        # Run callbacks
        callback_results: list[CallbackResult] = self._callback_runner.run_all(
            specs=self._config.callbacks,
            logs_dir=logs_dir,
            candidate_path=candidate_path,
        )

        all_passed = all(r.passed for r in callback_results)
        if all_passed:
            logger.debug("Orchestrator: all callbacks passed on iteration %d", iteration_idx)
            return IterationRecord(idx=iteration_idx, status=IterationStatus.PASSED)

        # Analyse failure and persist feedback
        new_feedback = self.analyze_failure(
            callback_results=callback_results,
            candidate_path=candidate_path,
            iteration_idx=iteration_idx,
        )
        self._workspace.memory.append_feedback(new_feedback)

        logger.debug(
            "Orchestrator: iteration %d FAILED — %s", iteration_idx, new_feedback.summary
        )
        return IterationRecord(
            idx=iteration_idx,
            status=IterationStatus.FAILED,
            feedback=new_feedback,
        )

    def analyze_failure(
        self,
        callback_results: list[CallbackResult],
        candidate_path: Path,
        iteration_idx: int,
    ) -> Feedback:
        """Delegate to :func:`~microbots.auto_memory.analyzer.analyze_failure`.

        Parameters
        ----------
        callback_results : list[CallbackResult]
            Results from the callback runner.
        candidate_path : Path
            Path to the candidate output for this iteration.
        iteration_idx : int
            Zero-based iteration index.

        Returns
        -------
        Feedback
            Structured failure summary.
        """
        return analyze_failure(
            callback_results=callback_results,
            candidate_path=candidate_path,
            iteration_idx=iteration_idx,
        )
