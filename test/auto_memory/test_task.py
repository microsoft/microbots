"""Unit tests for microbots.auto_memory.evalTask."""

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.evalTask import CallbackResult, EvalOutcome, EvalTask


class _RunOnlyTask(EvalTask):
    """A task that overrides only run()/build_feedback(), never touching the optional hooks."""

    @classmethod
    def from_config(cls, task_args):
        return [cls()]

    def run(self, repo_path, memory_dir, model, log_path):
        return EvalOutcome(
            passed=True,
            output="custom output",
            result=None,
        )

    def build_feedback(self, outcome, repo_path, model, log_path):
        return "feedback text"


@pytest.mark.unit
def test_run_is_abstract():
    with pytest.raises(TypeError):
        EvalTask()


@pytest.mark.unit
def test_build_feedback_is_abstract():
    class _MissingBuildFeedback(EvalTask):
        @classmethod
        def from_config(cls, task_args):
            return [cls()]

        def run(self, repo_path, memory_dir, model, log_path):
            raise NotImplementedError

    with pytest.raises(TypeError):
        _MissingBuildFeedback()


@pytest.mark.unit
def test_from_config_is_abstract():
    class _MissingFromConfig(EvalTask):
        def run(self, repo_path, memory_dir, model, log_path):
            raise NotImplementedError

        def build_feedback(self, outcome, repo_path, model, log_path):
            raise NotImplementedError

    with pytest.raises(TypeError):
        _MissingFromConfig()


@pytest.mark.unit
def test_from_config_default_body_raises_not_implemented_error():
    with pytest.raises(NotImplementedError):
        EvalTask.from_config({})


@pytest.mark.unit
def test_subclass_overriding_only_run_is_instantiable():
    task = _RunOnlyTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o", "/log")

    assert outcome.passed is True
    assert outcome.output == "custom output"


@pytest.mark.unit
def test_default_setup_is_a_noop():
    # Should not raise.
    _RunOnlyTask().setup("/repo")


@pytest.mark.unit
def test_default_teardown_is_a_noop():
    # Should not raise.
    _RunOnlyTask().teardown("/repo")


@pytest.mark.unit
def test_default_build_prompt_returns_empty_string():
    assert _RunOnlyTask().build_prompt() == ""


@pytest.mark.unit
def test_default_check_passes_by_default():
    result = _RunOnlyTask().check("/repo", "output", "/log")

    assert isinstance(result, CallbackResult)
    assert result.passed is True


@pytest.mark.unit
def test_default_task_id_is_class_name():
    assert _RunOnlyTask().task_id == "_RunOnlyTask"


@pytest.mark.unit
def test_default_build_result_returns_passed_and_reason():
    outcome = EvalOutcome(
        passed=False,
        output="agent output",
        result=CallbackResult(passed=False, reason="check failed"),
    )

    assert _RunOnlyTask().build_result(outcome) == {"passed": False, "reason": "check failed"}
