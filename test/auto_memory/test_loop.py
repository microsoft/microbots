"""Unit tests for the shared bounded iteration loop used by both orchestrators."""

from unittest.mock import patch

import pytest

from microbots.auto_memory.loop import StepOutcome, StopReason, run_bounded_loop

pytestmark = pytest.mark.unit


class _Boom(Exception):
    """Marker exception distinct from generic Exception for narrow-catch tests."""


def test_limit_reached_when_no_step_ever_stops():
    calls = []

    def step(idx):
        calls.append(idx)
        return StepOutcome(record=idx)

    result = run_bounded_loop(max_iterations=3, total_timeout_s=0, step=step)

    assert result.stop_reason == StopReason.LIMIT_REACHED
    assert result.iterations_run == 3
    assert result.records == [0, 1, 2]
    assert calls == [0, 1, 2]


def test_success_stop_ends_loop_immediately():
    def step(idx):
        stop = StopReason.SUCCESS if idx == 1 else None
        return StepOutcome(record=idx, stop=stop)

    result = run_bounded_loop(max_iterations=5, total_timeout_s=0, step=step)

    assert result.stop_reason == StopReason.SUCCESS
    assert result.iterations_run == 2
    assert result.records == [0, 1]


def test_total_timeout_stops_before_running_next_iteration():
    def step(idx):
        return StepOutcome(record=idx)

    with patch(
        "microbots.auto_memory.loop.time.monotonic",
        side_effect=[0.0, 0.0, 5.0, 61.0],
    ):
        result = run_bounded_loop(max_iterations=5, total_timeout_s=60, step=step)

    assert result.stop_reason == StopReason.TOTAL_TIMEOUT
    # The iteration that would have exceeded the budget never ran.
    assert result.iterations_run == 1
    assert result.records == [0]


def test_transient_error_retries_then_gives_up():
    attempts = []

    def step(idx):
        attempts.append(idx)
        return StepOutcome(record=idx, transient_error=True)

    result = run_bounded_loop(
        max_iterations=10,
        total_timeout_s=0,
        step=step,
        max_transient_retries=2,
    )

    assert result.stop_reason == StopReason.ERROR
    # 1 initial attempt + 2 retries = 3 iterations before giving up.
    assert result.iterations_run == 3
    assert attempts == [0, 1, 2]


def test_transient_error_counter_resets_after_a_healthy_iteration():
    statuses = [True, False, True, True]  # True == transient_error

    def step(idx):
        return StepOutcome(record=idx, transient_error=statuses[idx])

    result = run_bounded_loop(
        max_iterations=len(statuses),
        total_timeout_s=0,
        step=step,
        max_transient_retries=1,
    )

    # idx 0 transient (1/1, within budget) -> idx 1 healthy resets the
    # counter -> idx 2 transient (1/1, within budget) -> idx 3 transient
    # (2/1, exceeds budget) -> stop.
    assert result.stop_reason == StopReason.ERROR
    assert result.iterations_run == 4


def test_caught_exception_produces_error_result_and_record():
    def step(idx):
        raise _Boom("kaboom")

    def on_exception(idx, exc):
        return f"iter {idx} failed: {exc}"

    result = run_bounded_loop(
        max_iterations=5,
        total_timeout_s=0,
        step=step,
        catch_exceptions=(_Boom,),
        on_exception=on_exception,
    )

    assert result.stop_reason == StopReason.ERROR
    assert result.iterations_run == 1
    assert result.records == ["iter 0 failed: kaboom"]
    assert result.error_message == "kaboom"


def test_uncaught_exception_type_propagates():
    def step(idx):
        raise ValueError("not caught")

    with pytest.raises(ValueError, match="not caught"):
        run_bounded_loop(
            max_iterations=5,
            total_timeout_s=0,
            step=step,
            catch_exceptions=(_Boom,),
        )


def test_no_on_exception_callback_still_stops_without_a_record():
    def step(idx):
        raise _Boom("kaboom")

    result = run_bounded_loop(
        max_iterations=5,
        total_timeout_s=0,
        step=step,
        catch_exceptions=(_Boom,),
    )

    assert result.stop_reason == StopReason.ERROR
    assert result.records == []
