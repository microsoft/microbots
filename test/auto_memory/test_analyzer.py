"""Tests for :func:`microbots.auto_memory.analyzer.analyze_failure`.

The analyzer delegates the failure-diagnosis narrative to
:class:`~microbots.bot.LogAnalysisBot.LogAnalysisBot`; the bot is patched
in these tests to keep them fast and offline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.MicroBot import BotRunResult
from microbots.auto_memory.analyzer import _LOG_TAIL_BYTES, _safe_read, analyze_failure
from microbots.auto_memory.callbacks import CallbackResult
from microbots.auto_memory.data_models import CallbackSpec, Feedback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANALYZER_KWARGS = {
    "analyzer_model": "azure-openai/gpt-4o",
    "analyzer_max_iterations": 5,
    "analyzer_timeout_s": 30,
}


def _spec(name: str = "tests", expected_rc: int = 0, timeout_s: int = 120) -> CallbackSpec:
    return CallbackSpec(
        name=name, command="pytest", timeout_s=timeout_s, expected_return_code=expected_rc
    )


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


def _patched_bot(
    *,
    status: bool = True,
    result: str | None = "diagnosis narrative",
    error: str | None = None,
    raises: Exception | None = None,
):
    """Return a patcher for LogAnalysisBot with a controllable BotRunResult."""
    bot_instance = MagicMock()
    if raises is not None:
        bot_instance.run.side_effect = raises
    else:
        bot_instance.run.return_value = BotRunResult(
            status=status, result=result, error=error
        )
    return patch(
        "microbots.auto_memory.analyzer.LogAnalysisBot",
        return_value=bot_instance,
    ), bot_instance


# ---------------------------------------------------------------------------
# All callbacks passed (short-circuit — bot is NOT invoked)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFailureAllPassed:
    def test_returns_feedback(self, tmp_path):
        results = [_result(tmp_path, "a"), _result(tmp_path, "b")]
        fb = analyze_failure(
            results, tmp_path / "cand", iteration_idx=0, **_ANALYZER_KWARGS
        )
        assert isinstance(fb, Feedback)

    def test_summary_says_all_passed(self, tmp_path):
        results = [_result(tmp_path, "a"), _result(tmp_path, "b")]
        fb = analyze_failure(
            results, tmp_path / "cand", iteration_idx=0, **_ANALYZER_KWARGS
        )
        assert fb.summary == "All callbacks passed."

    def test_no_validator_failures(self, tmp_path):
        results = [_result(tmp_path, "tests")]
        fb = analyze_failure(
            results, tmp_path / "cand", iteration_idx=0, **_ANALYZER_KWARGS
        )
        assert fb.validator_failures == []

    def test_no_root_causes(self, tmp_path):
        results = [_result(tmp_path, "lint")]
        fb = analyze_failure(
            results, tmp_path / "cand", iteration_idx=0, **_ANALYZER_KWARGS
        )
        assert fb.root_causes == []

    def test_iteration_idx_stored(self, tmp_path):
        results = [_result(tmp_path, "tests")]
        fb = analyze_failure(
            results, tmp_path / "cand", iteration_idx=2, **_ANALYZER_KWARGS
        )
        assert fb.iteration_idx == 2

    def test_bot_not_invoked_when_all_pass(self, tmp_path):
        patcher, bot_instance = _patched_bot()
        with patcher:
            analyze_failure(
                [_result(tmp_path, "tests", passed=True)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        bot_instance.run.assert_not_called()


# ---------------------------------------------------------------------------
# Some callbacks failed — happy path (bot returns a narrative)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFailureBotSucceeds:
    def test_summary_is_bot_result(self, tmp_path):
        patcher, _ = _patched_bot(result="Root cause: missing return statement.")
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert fb.summary == "Root cause: missing return statement."

    def test_validator_failures_lists_failed_names(self, tmp_path):
        patcher, _ = _patched_bot()
        results = [
            _result(tmp_path, "unit_tests", passed=True),
            _result(tmp_path, "lint", passed=False, return_code=1),
        ]
        with patcher:
            fb = analyze_failure(
                results, tmp_path / "cand", iteration_idx=0, **_ANALYZER_KWARGS
            )
        assert fb.validator_failures == ["lint"]

    def test_root_causes_empty_on_success(self, tmp_path):
        patcher, _ = _patched_bot()
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert fb.root_causes == []

    def test_bot_result_is_stripped(self, tmp_path):
        patcher, _ = _patched_bot(result="   narrative with padding   \n")
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert fb.summary == "narrative with padding"

    def test_iteration_idx_preserved(self, tmp_path):
        patcher, _ = _patched_bot()
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=4,
                **_ANALYZER_KWARGS,
            )
        assert fb.iteration_idx == 4

    def test_bot_invoked_with_configured_model_and_limits(self, tmp_path):
        patcher, bot_instance = _patched_bot()
        with patch(
            "microbots.auto_memory.analyzer.LogAnalysisBot",
            return_value=bot_instance,
        ) as mock_ctor:
            analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                analyzer_model="azure-openai/gpt-4o-mini",
                analyzer_max_iterations=7,
                analyzer_timeout_s=99,
            )
        # Constructor received model + mount folder.
        ctor_kwargs = mock_ctor.call_args.kwargs
        assert ctor_kwargs["model"] == "azure-openai/gpt-4o-mini"
        assert "folder_to_mount" in ctor_kwargs
        # run() received the configured iteration + timeout.
        run_kwargs = bot_instance.run.call_args.kwargs
        assert run_kwargs["max_iterations"] == 7
        assert run_kwargs["timeout_in_seconds"] == 99

    def test_bot_mounts_candidate_dir_when_it_exists(self, tmp_path):
        cand_dir = tmp_path / "cand"
        cand_dir.mkdir()
        patcher, bot_instance = _patched_bot()
        with patch(
            "microbots.auto_memory.analyzer.LogAnalysisBot",
            return_value=bot_instance,
        ) as mock_ctor:
            analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                cand_dir,
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert mock_ctor.call_args.kwargs["folder_to_mount"] == str(cand_dir)

    def test_bot_mounts_parent_when_candidate_missing(self, tmp_path):
        cand_dir = tmp_path / "missing_candidate"  # not created
        patcher, bot_instance = _patched_bot()
        with patch(
            "microbots.auto_memory.analyzer.LogAnalysisBot",
            return_value=bot_instance,
        ) as mock_ctor:
            analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                cand_dir,
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert mock_ctor.call_args.kwargs["folder_to_mount"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Bot failed to produce a result
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFailureBotNoResult:
    def test_root_cause_reports_unknown_when_no_error(self, tmp_path):
        patcher, _ = _patched_bot(status=False, result=None, error=None)
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert any("unknown" in c for c in fb.root_causes)

    def test_root_cause_includes_bot_error(self, tmp_path):
        patcher, _ = _patched_bot(status=False, result=None, error="bot bailed")
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert any("bot bailed" in c for c in fb.root_causes)

    def test_summary_falls_back_to_count(self, tmp_path):
        patcher, _ = _patched_bot(status=False, result=None, error="bot bailed")
        with patcher:
            fb = analyze_failure(
                [
                    _result(tmp_path, "a", passed=False, return_code=1),
                    _result(tmp_path, "b", passed=False, return_code=2),
                ],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert "2 of 2" in fb.summary
        assert "a" in fb.summary and "b" in fb.summary

    def test_validator_failures_still_populated(self, tmp_path):
        patcher, _ = _patched_bot(status=False, result=None, error="x")
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "lint", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert fb.validator_failures == ["lint"]

    def test_empty_result_treated_as_no_result(self, tmp_path):
        # status=True but result="" is falsy → same "did not produce a result" path.
        patcher, _ = _patched_bot(status=True, result="", error=None)
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert any("did not produce a result" in c for c in fb.root_causes)


# ---------------------------------------------------------------------------
# Bot invocation itself raised
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFailureBotRaises:
    def test_exception_is_captured_in_root_causes(self, tmp_path):
        patcher, _ = _patched_bot(raises=RuntimeError("network down"))
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert any("network down" in c for c in fb.root_causes)
        assert any("LLM analyzer error" in c for c in fb.root_causes)

    def test_summary_falls_back_on_exception(self, tmp_path):
        patcher, _ = _patched_bot(raises=RuntimeError("boom"))
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert "1 of 1" in fb.summary
        assert "tests" in fb.summary

    def test_validator_failures_still_populated_on_exception(self, tmp_path):
        patcher, _ = _patched_bot(raises=RuntimeError("boom"))
        with patcher:
            fb = analyze_failure(
                [_result(tmp_path, "tests", passed=False, return_code=1)],
                tmp_path / "cand",
                iteration_idx=1,
                **_ANALYZER_KWARGS,
            )
        assert fb.validator_failures == ["tests"]
        assert fb.iteration_idx == 1


# ---------------------------------------------------------------------------
# _safe_read — OSError fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSafeReadOSError:
    def test_missing_log_files_do_not_raise(self, tmp_path):
        """OSError on missing log files must be swallowed by _safe_read.

        We drive it through the public API by pointing a failed
        CallbackResult at non-existent log paths and letting the analyzer
        combine them into its temp log before handing it to the (mocked)
        bot.
        """
        spec = _spec("mycheck", expected_rc=0)
        result = CallbackResult(
            spec=spec,
            return_code=5,
            stdout_path=tmp_path / "nonexistent.stdout",
            stderr_path=tmp_path / "nonexistent.stderr",
            passed=False,
        )
        patcher, _ = _patched_bot(result="ok")
        with patcher:
            fb = analyze_failure(
                [result],
                tmp_path / "cand",
                iteration_idx=0,
                **_ANALYZER_KWARGS,
            )
        assert fb.validator_failures == ["mycheck"]
        assert fb.summary == "ok"


# ---------------------------------------------------------------------------
# _safe_read — tail-truncation cap
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSafeReadTailCap:
    def test_small_file_returned_verbatim(self, tmp_path):
        p = tmp_path / "small.log"
        p.write_text("hello world")
        assert _safe_read(p) == "hello world"

    def test_default_cap_is_applied(self, tmp_path):
        p = tmp_path / "big.log"
        # Head + tail with a distinct marker so we can verify only the tail returned.
        payload = ("A" * (_LOG_TAIL_BYTES + 100)) + "TAIL_MARKER"
        p.write_text(payload)
        out = _safe_read(p)
        assert out.startswith("<truncated: showing last ")
        assert "TAIL_MARKER" in out
        # Kept bytes must not exceed the cap.
        body = out.split("\n", 1)[1]
        assert len(body.encode("utf-8")) <= _LOG_TAIL_BYTES

    def test_custom_cap(self, tmp_path):
        p = tmp_path / "custom.log"
        p.write_text("x" * 100 + "END")
        out = _safe_read(p, max_bytes=10)
        assert out.startswith("<truncated: showing last 10 bytes of 103>\n")
        assert out.endswith("xxxxxxxEND")

    def test_cap_zero_disables_truncation(self, tmp_path):
        p = tmp_path / "full.log"
        payload = "y" * (_LOG_TAIL_BYTES + 50)
        p.write_text(payload)
        assert _safe_read(p, max_bytes=0) == payload

    def test_truncation_marker_reports_total_size(self, tmp_path):
        p = tmp_path / "sized.log"
        p.write_text("z" * 500)
        out = _safe_read(p, max_bytes=100)
        assert "of 500>" in out
