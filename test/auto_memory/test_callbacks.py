import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from microbots.auto_memory.callbacks import CallbackResult, CallbackRunner, ShellCallbackRunner
from microbots.auto_memory.data_models import CallbackSpec
from microbots.auto_memory.errors import CallbackError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(name: str = "tests", command: str = "pytest", *, timeout_s: int = 120, expected_rc: int = 0) -> CallbackSpec:
    return CallbackSpec(name=name, command=command, timeout_s=timeout_s, expected_return_code=expected_rc)


def _make_proc(returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# CallbackResult data model
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCallbackResult:
    def test_passed_true_when_rc_matches(self, tmp_path):
        spec = _spec()
        result = CallbackResult(
            spec=spec,
            return_code=0,
            stdout_path=tmp_path / "out",
            stderr_path=tmp_path / "err",
            passed=True,
        )
        assert result.passed is True
        assert result.timed_out is False
        assert result.duration_s == 0.0

    def test_passed_false_when_timed_out(self, tmp_path):
        spec = _spec()
        result = CallbackResult(
            spec=spec,
            return_code=-1,
            stdout_path=tmp_path / "out",
            stderr_path=tmp_path / "err",
            passed=False,
            timed_out=True,
        )
        assert result.passed is False
        assert result.timed_out is True


# ---------------------------------------------------------------------------
# CallbackRunner ABC contract
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCallbackRunnerABC:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            CallbackRunner()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_run_all(self):
        class Incomplete(CallbackRunner):
            pass
        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ShellCallbackRunner — happy-path (mock subprocess.run)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShellCallbackRunnerRunAll:
    def test_returns_one_result_per_spec(self, tmp_path):
        specs = [_spec("a"), _spec("b"), _spec("c")]
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            runner = ShellCallbackRunner()
            results = runner.run_all(specs, logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert len(results) == 3

    def test_results_in_same_order_as_specs(self, tmp_path):
        specs = [_spec("first"), _spec("second")]
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            runner = ShellCallbackRunner()
            results = runner.run_all(specs, logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert results[0].spec.name == "first"
        assert results[1].spec.name == "second"

    def test_passing_callback_has_passed_true(self, tmp_path):
        spec = _spec(expected_rc=0)
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            runner = ShellCallbackRunner()
            results = runner.run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert results[0].passed is True

    def test_failing_rc_has_passed_false(self, tmp_path):
        spec = _spec(expected_rc=0)
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(1)):
            runner = ShellCallbackRunner()
            results = runner.run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert results[0].passed is False
        assert results[0].return_code == 1
        assert results[0].timed_out is False

    def test_custom_expected_rc(self, tmp_path):
        spec = _spec(expected_rc=2)
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(2)):
            runner = ShellCallbackRunner()
            results = runner.run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert results[0].passed is True

    def test_stdout_stderr_paths_set_correctly(self, tmp_path):
        spec = _spec("lint")
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            runner = ShellCallbackRunner()
            results = runner.run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert results[0].stdout_path == tmp_path / "lint.stdout"
        assert results[0].stderr_path == tmp_path / "lint.stderr"

    def test_stdout_stderr_files_created(self, tmp_path):
        spec = _spec("lint")
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            runner = ShellCallbackRunner()
            runner.run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "cand")
        assert (tmp_path / "lint.stdout").exists()
        assert (tmp_path / "lint.stderr").exists()

    def test_candidate_path_passed_in_env(self, tmp_path):
        spec = _spec()
        candidate = tmp_path / "my_candidate"
        captured_env = {}

        def fake_run(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return _make_proc(0)

        with patch("microbots.auto_memory.callbacks.subprocess.run", side_effect=fake_run):
            ShellCallbackRunner().run_all([spec], logs_dir=tmp_path, candidate_path=candidate)

        assert captured_env.get("CANDIDATE") == str(candidate)

    def test_shell_true_used(self, tmp_path):
        spec = _spec()
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)) as mock_run:
            ShellCallbackRunner().run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "c")
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is True

    def test_duration_s_is_non_negative(self, tmp_path):
        with patch("microbots.auto_memory.callbacks.subprocess.run", return_value=_make_proc(0)):
            results = ShellCallbackRunner().run_all([_spec()], logs_dir=tmp_path, candidate_path=tmp_path / "c")
        assert results[0].duration_s >= 0.0


# ---------------------------------------------------------------------------
# ShellCallbackRunner — timeout
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShellCallbackRunnerTimeout:
    def test_timeout_sets_timed_out_flag(self, tmp_path):
        spec = _spec(timeout_s=1)
        with patch(
            "microbots.auto_memory.callbacks.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=1),
        ):
            results = ShellCallbackRunner().run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "c")
        assert results[0].timed_out is True
        assert results[0].passed is False

    def test_timeout_return_code_is_negative_one(self, tmp_path):
        spec = _spec()
        with patch(
            "microbots.auto_memory.callbacks.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
        ):
            results = ShellCallbackRunner().run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "c")
        assert results[0].return_code == -1

    def test_remaining_specs_still_run_after_timeout(self, tmp_path):
        specs = [_spec("slow"), _spec("fast")]
        side_effects = [
            subprocess.TimeoutExpired(cmd="slow", timeout=1),
            _make_proc(0),
        ]
        with patch("microbots.auto_memory.callbacks.subprocess.run", side_effect=side_effects):
            results = ShellCallbackRunner().run_all(specs, logs_dir=tmp_path, candidate_path=tmp_path / "c")
        assert results[0].timed_out is True
        assert results[1].passed is True


# ---------------------------------------------------------------------------
# ShellCallbackRunner — spawn error
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShellCallbackRunnerSpawnError:
    def test_os_error_raises_callback_error(self, tmp_path):
        spec = _spec()
        with patch(
            "microbots.auto_memory.callbacks.subprocess.run",
            side_effect=OSError("no such file"),
        ):
            with pytest.raises(CallbackError, match="no such file"):
                ShellCallbackRunner().run_all([spec], logs_dir=tmp_path, candidate_path=tmp_path / "c")
