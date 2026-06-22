import pytest
from pathlib import Path

from microbots.auto_memory.analyzer import analyze_failure
from microbots.auto_memory.callbacks import CallbackResult
from microbots.auto_memory.data_models import CallbackSpec, Feedback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(name: str = "tests", expected_rc: int = 0, timeout_s: int = 120) -> CallbackSpec:
    return CallbackSpec(name=name, command="pytest", timeout_s=timeout_s, expected_return_code=expected_rc)


def _result(
    tmp_path: Path,
    name: str = "tests",
    *,
    passed: bool = True,
    return_code: int = 0,
    timed_out: bool = False,
    stderr_content: str = "",
    stdout_content: str = "",
    expected_rc: int = 0,
    timeout_s: int = 120,
) -> CallbackResult:
    stdout_path = tmp_path / f"{name}.stdout"
    stderr_path = tmp_path / f"{name}.stderr"
    stdout_path.write_text(stdout_content, encoding="utf-8")
    stderr_path.write_text(stderr_content, encoding="utf-8")
    return CallbackResult(
        spec=_spec(name=name, expected_rc=expected_rc, timeout_s=timeout_s),
        return_code=return_code,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        passed=passed,
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# All callbacks passed
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFailureAllPassed:
    def test_returns_feedback(self, tmp_path):
        results = [_result(tmp_path, "a"), _result(tmp_path, "b")]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert isinstance(fb, Feedback)

    def test_summary_says_all_passed(self, tmp_path):
        results = [_result(tmp_path, "a"), _result(tmp_path, "b")]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert fb.summary == "All callbacks passed."

    def test_no_validator_failures(self, tmp_path):
        results = [_result(tmp_path, "tests")]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert fb.validator_failures == []

    def test_no_root_causes(self, tmp_path):
        results = [_result(tmp_path, "lint")]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert fb.root_causes == []

    def test_iteration_idx_stored(self, tmp_path):
        results = [_result(tmp_path, "tests")]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=2)
        assert fb.iteration_idx == 2


# ---------------------------------------------------------------------------
# Some callbacks failed (non-timeout)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFailureWithFailures:
    def test_validator_failures_lists_failed_names(self, tmp_path):
        results = [
            _result(tmp_path, "unit_tests", passed=True),
            _result(tmp_path, "lint", passed=False, return_code=1),
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert "lint" in fb.validator_failures
        assert "unit_tests" not in fb.validator_failures

    def test_summary_includes_count_and_names(self, tmp_path):
        results = [
            _result(tmp_path, "a", passed=False, return_code=1),
            _result(tmp_path, "b", passed=False, return_code=2),
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert "2 of 2" in fb.summary
        assert "a" in fb.summary
        assert "b" in fb.summary

    def test_root_cause_includes_stderr_snippet(self, tmp_path):
        results = [
            _result(
                tmp_path, "tests",
                passed=False, return_code=1,
                stderr_content="AssertionError: expected 42",
            )
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert any("AssertionError" in c for c in fb.root_causes)

    def test_root_cause_falls_back_to_stdout(self, tmp_path):
        results = [
            _result(
                tmp_path, "tests",
                passed=False, return_code=1,
                stderr_content="",
                stdout_content="FAILED test_something.py::test_add",
            )
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert any("FAILED" in c for c in fb.root_causes)

    def test_root_cause_fallback_when_no_logs(self, tmp_path):
        result = _result(tmp_path, "mycheck", passed=False, return_code=3, expected_rc=0)
        # Wipe the log files so they are empty
        result.stderr_path.write_text("")
        result.stdout_path.write_text("")
        fb = analyze_failure([result], tmp_path / "cand", iteration_idx=0)
        assert any("3" in c for c in fb.root_causes)  # exit code 3 mentioned

    def test_mixed_pass_fail_summary(self, tmp_path):
        results = [
            _result(tmp_path, "unit", passed=True),
            _result(tmp_path, "e2e", passed=False, return_code=1),
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=1)
        assert "1 of 2" in fb.summary

    def test_one_root_cause_per_failed_callback(self, tmp_path):
        results = [
            _result(tmp_path, "a", passed=False, return_code=1),
            _result(tmp_path, "b", passed=False, return_code=1),
        ]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert len(fb.root_causes) == 2


# ---------------------------------------------------------------------------
# Timed-out callbacks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFailureTimeout:
    def test_timed_out_callback_in_validator_failures(self, tmp_path):
        results = [_result(tmp_path, "slow", passed=False, return_code=-1, timed_out=True, timeout_s=30)]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert "slow" in fb.validator_failures

    def test_timed_out_root_cause_mentions_timeout(self, tmp_path):
        results = [_result(tmp_path, "slow", passed=False, return_code=-1, timed_out=True, timeout_s=30)]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert any("timed out" in c for c in fb.root_causes)

    def test_timed_out_root_cause_mentions_timeout_seconds(self, tmp_path):
        results = [_result(tmp_path, "slow", passed=False, return_code=-1, timed_out=True, timeout_s=45)]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert any("45" in c for c in fb.root_causes)

    def test_timed_out_suggested_action_present(self, tmp_path):
        results = [_result(tmp_path, "slow", passed=False, return_code=-1, timed_out=True)]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert len(fb.suggested_actions) >= 1

    def test_timed_out_suggested_action_mentions_callback_name(self, tmp_path):
        results = [_result(tmp_path, "bigtest", passed=False, return_code=-1, timed_out=True)]
        fb = analyze_failure(results, tmp_path / "cand", iteration_idx=0)
        assert any("bigtest" in a for a in fb.suggested_actions)
