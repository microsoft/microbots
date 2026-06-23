"""Tests for TrainingLoopOrchestrator — all 5 termination paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory.callbacks import CallbackResult, CallbackRunner
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.data_models import (
    CallbackSpec,
    FinalStatus,
    IterationStatus,
)
from microbots.auto_memory.errors import AgentError
from microbots.auto_memory.orchestrator import RunSummary, TrainingLoopOrchestrator
from microbots.auto_memory.runners.base import AgentResult, AgentRunner
from microbots.auto_memory.workspace import WorkspaceManager


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_config(
    *,
    max_iterations: int = 5,
    timeout_min: int = 60,
    per_iteration_timeout: int = 600,
) -> TaskConfig:
    """Minimal TaskConfig suitable for unit tests."""
    return TaskConfig(
        task_definition="Write hello world",
        prompt_template="{{ task }}",
        callbacks=[CallbackSpec(name="check", command="echo ok")],
        max_iterations=max_iterations,
        timeout_min=timeout_min,
        per_iteration_timeout=per_iteration_timeout,
    )


def _make_agent_result(status: IterationStatus, *, error: str | None = None) -> AgentResult:
    return AgentResult(
        status=status,
        output="output" if status == IterationStatus.PASSED else None,
        error=error,
    )


def _make_callback_result(tmp_path: Path, *, passed: bool = True) -> CallbackResult:
    spec = CallbackSpec(name="check", command="echo ok")
    tmp_path.mkdir(parents=True, exist_ok=True)
    stdout = tmp_path / "check.stdout"
    stderr = tmp_path / "check.stderr"
    stdout.write_text("")
    stderr.write_text("")
    return CallbackResult(
        spec=spec,
        return_code=0 if passed else 1,
        stdout_path=stdout,
        stderr_path=stderr,
        passed=passed,
    )


class MockAgentRunner:
    """Controllable AgentRunner that returns results from a pre-configured queue."""

    def __init__(self, results: list[AgentResult]) -> None:
        self._results = list(results)
        self._calls: list[tuple] = []

    def run(self, ctx, timeout_s: int) -> AgentResult:
        self._calls.append((ctx, timeout_s))
        if not self._results:
            raise AgentError("MockAgentRunner: no more results configured")
        return self._results.pop(0)

    @property
    def call_count(self) -> int:
        return len(self._calls)


class RaisingAgentRunner:
    """AgentRunner that always raises AgentError."""

    def __init__(self, message: str = "agent exploded") -> None:
        self._message = message

    def run(self, ctx, timeout_s: int) -> AgentResult:
        raise AgentError(self._message)


class MockCallbackRunner:
    """Controllable CallbackRunner."""

    def __init__(self, results_per_call: list[list[CallbackResult]]) -> None:
        """Each inner list is returned on successive run_all() calls."""
        self._results = list(results_per_call)
        self._calls: list[tuple] = []

    def run_all(self, specs, logs_dir, candidate_path) -> list[CallbackResult]:
        self._calls.append((specs, logs_dir, candidate_path))
        if not self._results:
            raise RuntimeError("MockCallbackRunner: no more results configured")
        return self._results.pop(0)

    @property
    def call_count(self) -> int:
        return len(self._calls)


def _build_orchestrator(
    config: TaskConfig,
    agent_runner: AgentRunner,
    callback_runner: CallbackRunner,
    tmp_path: Path,
) -> TrainingLoopOrchestrator:
    workspace = WorkspaceManager(run_dir=tmp_path / "run")
    return TrainingLoopOrchestrator(
        config=config,
        agent_runner=agent_runner,
        callback_runner=callback_runner,
        workspace=workspace,
    )


# ---------------------------------------------------------------------------
# PATH 1: PASSED — agent succeeds and all callbacks pass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPassedPath:
    def test_final_status_is_passed(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.PASSED)])
        callbacks = MockCallbackRunner([[_make_callback_result(tmp_path, passed=True)]])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.PASSED

    def test_iterations_run_is_one(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.PASSED)])
        callbacks = MockCallbackRunner([[_make_callback_result(tmp_path, passed=True)]])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.iterations_run == 1

    def test_agent_called_once(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.PASSED)])
        callbacks = MockCallbackRunner([[_make_callback_result(tmp_path, passed=True)]])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        orch.run()

        assert agent.call_count == 1

    def test_passed_on_second_attempt(self, tmp_path):
        """Agent fails then passes — status must be PASSED after 2 iterations."""
        config = _make_config()
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=True)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.PASSED
        assert summary.iterations_run == 2


# ---------------------------------------------------------------------------
# PATH 2: FAILED → retry (callback fails but retries remain)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFailedRetryPath:
    def test_callback_failure_triggers_retry(self, tmp_path):
        config = _make_config(max_iterations=3)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=False)],
            [_make_callback_result(tmp_path / "c", passed=True)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.PASSED
        assert summary.iterations_run == 3

    def test_feedback_persisted_after_failure(self, tmp_path):
        config = _make_config(max_iterations=2)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=True)],
        ])
        workspace = WorkspaceManager(run_dir=tmp_path / "run")
        orch = TrainingLoopOrchestrator(
            config=config,
            agent_runner=agent,
            callback_runner=callbacks,
            workspace=workspace,
        )

        orch.run()

        # One feedback entry must have been written to the memory store
        feedback_entries = workspace.memory.read_all()
        assert len(feedback_entries) == 1
        assert feedback_entries[0].iteration_idx == 0

    def test_failed_record_has_feedback(self, tmp_path):
        config = _make_config(max_iterations=2)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=True)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        failed_records = [r for r in summary.iteration_records if r.status == IterationStatus.FAILED]
        assert len(failed_records) == 1
        assert failed_records[0].feedback is not None


# ---------------------------------------------------------------------------
# PATH 3: LIMIT_REACHED — all iterations exhausted without a pass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLimitReachedPath:
    def test_final_status_is_limit_reached(self, tmp_path):
        config = _make_config(max_iterations=3)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=False)],
            [_make_callback_result(tmp_path / "c", passed=False)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.LIMIT_REACHED

    def test_iterations_run_equals_max_iterations(self, tmp_path):
        config = _make_config(max_iterations=3)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=False)],
            [_make_callback_result(tmp_path / "c", passed=False)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.iterations_run == 3

    def test_all_records_have_failed_status(self, tmp_path):
        config = _make_config(max_iterations=2)
        agent = MockAgentRunner([
            _make_agent_result(IterationStatus.PASSED),
            _make_agent_result(IterationStatus.PASSED),
        ])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
            [_make_callback_result(tmp_path / "b", passed=False)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert all(r.status == IterationStatus.FAILED for r in summary.iteration_records)


# ---------------------------------------------------------------------------
# PATH 4: TIMEOUT — total wall-clock limit exceeded between iterations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTimeoutPath:
    def test_final_status_is_timeout_when_total_elapsed(self, tmp_path):
        """Simulate total timeout expiring before the second iteration begins."""
        config = _make_config(max_iterations=5, timeout_min=1)
        agent = MockAgentRunner([_make_agent_result(IterationStatus.PASSED)])
        callbacks = MockCallbackRunner([
            [_make_callback_result(tmp_path / "a", passed=False)],
        ])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        # Patch time.monotonic so it jumps past timeout after iteration 0
        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # First call (start_time) returns 0; next call returns timeout + 1
            return 0.0 if call_count == 1 else config.timeout_min * 60 + 1.0

        with patch("microbots.auto_memory.orchestrator.time.monotonic", side_effect=fake_monotonic):
            summary = orch.run()

        assert summary.final_status == FinalStatus.TIMEOUT

    def test_per_iteration_timeout_yields_timeout_status(self, tmp_path):
        """Agent itself times out → final status TIMEOUT."""
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.TIMEOUT)])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.TIMEOUT

    def test_per_iteration_timeout_callbacks_not_called(self, tmp_path):
        """Callbacks must not be invoked when the agent itself times out."""
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.TIMEOUT)])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        orch.run()

        assert callbacks.call_count == 0

    def test_timeout_iterations_run_reflects_completed(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.TIMEOUT)])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        # One iteration was started and returned TIMEOUT
        assert summary.iterations_run == 1


# ---------------------------------------------------------------------------
# PATH 5: AGENT_ERROR — runner raises AgentError or returns ERROR status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentErrorPath:
    def test_raised_agent_error_yields_error_status(self, tmp_path):
        config = _make_config()
        agent = RaisingAgentRunner("disk full")
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.ERROR

    def test_raised_agent_error_message_captured(self, tmp_path):
        config = _make_config()
        agent = RaisingAgentRunner("disk full")
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert "disk full" in (summary.error_message or "")

    def test_returned_error_status_yields_error(self, tmp_path):
        """Agent returns IterationStatus.ERROR → RunSummary.final_status == ERROR."""
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.ERROR, error="OOM")])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.final_status == FinalStatus.ERROR

    def test_returned_error_callbacks_not_called(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.ERROR, error="OOM")])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        orch.run()

        assert callbacks.call_count == 0

    def test_error_iterations_run_is_one(self, tmp_path):
        config = _make_config()
        agent = MockAgentRunner([_make_agent_result(IterationStatus.ERROR, error="OOM")])
        callbacks = MockCallbackRunner([])
        orch = _build_orchestrator(config, agent, callbacks, tmp_path)

        summary = orch.run()

        assert summary.iterations_run == 1


# ---------------------------------------------------------------------------
# RunSummary data model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunSummary:
    def test_defaults(self):
        s = RunSummary(final_status=FinalStatus.PASSED, iterations_run=1)
        assert s.iteration_records == []
        assert s.elapsed_s == 0.0
        assert s.error_message is None

    def test_is_dataclass(self):
        s = RunSummary(final_status=FinalStatus.ERROR, iterations_run=0, error_message="boom")
        assert s.final_status == FinalStatus.ERROR
        assert s.error_message == "boom"


# ---------------------------------------------------------------------------
# analyze_failure delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFailureDelegation:
    def test_delegates_to_module_function(self, tmp_path):
        config = _make_config()
        workspace = WorkspaceManager(run_dir=tmp_path / "run")
        workspace.prepare()
        workspace.prepare_iteration(0)

        orch = TrainingLoopOrchestrator(
            config=config,
            agent_runner=MockAgentRunner([]),
            callback_runner=MockCallbackRunner([]),
            workspace=workspace,
        )

        cb_result = _make_callback_result(tmp_path, passed=False)

        with patch(
            "microbots.auto_memory.orchestrator.analyze_failure",
            return_value=MagicMock(),
        ) as mock_analyze:
            orch.analyze_failure(
                callback_results=[cb_result],
                candidate_path=tmp_path / "cand",
                iteration_idx=0,
            )

        mock_analyze.assert_called_once_with(
            callback_results=[cb_result],
            candidate_path=tmp_path / "cand",
            iteration_idx=0,
        )
