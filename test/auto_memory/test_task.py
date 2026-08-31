"""Unit tests for microbots.auto_memory.task."""

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.task import CallbackResult, EvalOutcome, EvalTask


class _RunOnlyTask(EvalTask):
    """A task that overrides only run(), never touching the optional hooks."""

    def run(self, repo_path, memory_dir, model):
        return EvalOutcome(
            passed=True,
            output="custom output",
            result=None,
            log_path="/dev/null",
        )


@pytest.mark.unit
def test_run_is_abstract():
    with pytest.raises(TypeError):
        EvalTask()


@pytest.mark.unit
def test_subclass_overriding_only_run_is_instantiable():
    task = _RunOnlyTask()
    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

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
    assert _RunOnlyTask().build_prompt("/repo") == ""


@pytest.mark.unit
def test_default_check_passes_by_default():
    result = _RunOnlyTask().check("/repo", "output", "/log")

    assert isinstance(result, CallbackResult)
    assert result.passed is True
