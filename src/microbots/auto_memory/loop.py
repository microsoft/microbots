"""Shared bounded, timed iteration-loop skeleton.

:class:`~microbots.auto_memory.orchestrator.TrainingLoopOrchestrator` (the
eval loop) and :class:`~microbots.auto_memory.training.orchestrator.TrainingOrchestrator`
(the training loop) both repeatedly invoke a "do one iteration" step,
enforce a total wall-clock timeout, translate an iteration-supplied stop
signal (pass / fail / timeout) into a run-level result, and normalise
unexpected exceptions into an error record. That control flow is
identical between the two loops even though what happens *inside* one
iteration (callbacks + feedback vs. prompt + memory notes) is completely
different.

This module owns exactly the shared control flow via :func:`run_bounded_loop`.
It knows nothing about bots, callbacks, or memory — those concerns stay in
the concrete orchestrators, which remain separate and independently
configurable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from logging import getLogger
from typing import Callable, Generic, TypeVar

logger = getLogger(__name__)

RecordT = TypeVar("RecordT")


class StopReason(StrEnum):
    """Why a bounded loop stopped iterating.

    ``SUCCESS`` and ``ITERATION_TIMEOUT`` are only ever produced by the
    caller's ``step`` callable; ``LIMIT_REACHED``, ``TOTAL_TIMEOUT``, and
    ``ERROR`` (from an uncaught exception) are produced by the loop itself.
    """

    SUCCESS = "success"
    LIMIT_REACHED = "limit_reached"
    TOTAL_TIMEOUT = "total_timeout"
    ITERATION_TIMEOUT = "iteration_timeout"
    ERROR = "error"


@dataclass
class StepOutcome(Generic[RecordT]):
    """Result of one loop step, returned by the caller-supplied ``step`` callable.

    Attributes
    ----------
    record : RecordT
        Caller-defined per-iteration record; always appended to the run's
        record list regardless of ``stop``/``transient_error``.
    stop : StopReason | None, optional
        When set, the loop stops immediately after this iteration and the
        run finishes with this reason. ``None`` means "keep looping".
        Ignored when ``transient_error`` is ``True`` and the retry budget
        has not yet been exhausted.
    transient_error : bool, optional
        When ``True``, this iteration counts against
        ``max_transient_retries`` instead of stopping outright. Once the
        budget is exhausted the loop stops with :attr:`StopReason.ERROR`.
        A non-transient iteration resets the consecutive-retry counter.
    """

    record: RecordT
    stop: StopReason | None = None
    transient_error: bool = False


@dataclass
class LoopResult(Generic[RecordT]):
    """Outcome of a full :func:`run_bounded_loop` run."""

    stop_reason: StopReason
    iterations_run: int
    records: list[RecordT] = field(default_factory=list)
    elapsed_s: float = 0.0
    error_message: str | None = None


def run_bounded_loop(
    *,
    max_iterations: int,
    total_timeout_s: float,
    step: Callable[[int], StepOutcome[RecordT]],
    catch_exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_exception: Callable[[int, BaseException], RecordT] | None = None,
    max_transient_retries: int = 0,
) -> LoopResult[RecordT]:
    """Drive ``step`` for up to ``max_iterations``, honouring a total timeout.

    Before every iteration the elapsed wall-clock time is compared against
    ``total_timeout_s``; if it has been exceeded the loop stops with
    :attr:`StopReason.TOTAL_TIMEOUT` *without* running that iteration
    (``iterations_run`` reflects only completed iterations).

    If ``step`` raises one of ``catch_exceptions``, the loop stops with
    :attr:`StopReason.ERROR`; ``on_exception`` (if given) is called to build
    a final record for that iteration, and ``error_message`` is set to
    ``str(exc)``. Exceptions not in ``catch_exceptions`` propagate to the
    caller uncaught, exactly as if this loop were not there.

    A returned :class:`StepOutcome` with ``transient_error=True`` counts
    against ``max_transient_retries``: while the consecutive count is at or
    below the budget the loop continues to the next iteration; once
    exceeded it stops with :attr:`StopReason.ERROR` (``error_message`` is
    left ``None`` — callers typically derive a message from the last
    record). Any non-transient iteration resets the counter.

    Otherwise, ``step``'s ``stop`` value (if not ``None``) ends the loop
    immediately with that reason; ``None`` continues to the next iteration.
    If ``max_iterations`` is exhausted without a stop, the loop ends with
    :attr:`StopReason.LIMIT_REACHED`.

    Parameters
    ----------
    max_iterations : int
        Maximum number of iterations to run.
    total_timeout_s : float
        Total wall-clock budget for the whole loop, in seconds. A value
        ``<= 0`` disables the total-timeout check.
    step : Callable[[int], StepOutcome[RecordT]]
        Runs one iteration (given its zero-based index) and reports its
        outcome. May raise; see ``catch_exceptions``.
    catch_exceptions : tuple[type[BaseException], ...], optional
        Exception types that :func:`run_bounded_loop` intercepts and turns
        into a :attr:`StopReason.ERROR` result. Defaults to ``(Exception,)``.
        Pass a narrower tuple (e.g. ``(AgentError,)``) to let unrelated bugs
        propagate uncaught.
    on_exception : Callable[[int, BaseException], RecordT] | None, optional
        Builds the final record to append when ``step`` raises a caught
        exception. If omitted, no record is appended for that iteration.
    max_transient_retries : int, optional
        Number of consecutive ``transient_error=True`` outcomes to tolerate
        before stopping. Defaults to ``0`` (no retries — the first
        transient error stops the loop).

    Returns
    -------
    LoopResult[RecordT]
        The accumulated records, stop reason, elapsed time, and (when
        applicable) error message.
    """
    start = time.monotonic()
    records: list[RecordT] = []
    consecutive_transient = 0

    for idx in range(max_iterations):
        elapsed = time.monotonic() - start
        if total_timeout_s > 0 and elapsed >= total_timeout_s:
            logger.info(
                "Bounded loop: total timeout reached after %.1fs (limit %.0fs)",
                elapsed,
                total_timeout_s,
            )
            return LoopResult(StopReason.TOTAL_TIMEOUT, idx, records, elapsed)

        try:
            outcome = step(idx)
        except catch_exceptions as exc:  # noqa: BLE001 - intentionally caller-scoped
            elapsed = time.monotonic() - start
            if on_exception is not None:
                records.append(on_exception(idx, exc))
            logger.error("Bounded loop: iteration %d raised %s", idx, exc)
            return LoopResult(
                StopReason.ERROR, idx + 1, records, elapsed, error_message=str(exc)
            )

        records.append(outcome.record)
        elapsed = time.monotonic() - start

        if outcome.transient_error:
            consecutive_transient += 1
            if consecutive_transient <= max_transient_retries:
                logger.warning(
                    "Bounded loop: transient error on iteration %d (retry %d/%d), continuing",
                    idx,
                    consecutive_transient,
                    max_transient_retries,
                )
                continue
            return LoopResult(StopReason.ERROR, idx + 1, records, elapsed)

        consecutive_transient = 0

        if outcome.stop is not None:
            return LoopResult(outcome.stop, idx + 1, records, elapsed)

    elapsed = time.monotonic() - start
    return LoopResult(StopReason.LIMIT_REACHED, max_iterations, records, elapsed)
