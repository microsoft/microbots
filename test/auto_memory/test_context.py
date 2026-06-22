import pytest

from microbots.auto_memory.context import build_iteration_context
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.data_models import CallbackSpec, Feedback, ReferenceInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(prompt_template: str, *, reference_inputs: list[ReferenceInput] | None = None) -> TaskConfig:
    return TaskConfig(
        task_definition="Fix the auth bug",
        prompt_template=prompt_template,
        callbacks=[CallbackSpec(name="tests", command="pytest")],
        reference_inputs=reference_inputs or [],
    )


# ---------------------------------------------------------------------------
# Rendering without feedback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildIterationContextNoFeedback:
    def test_task_substituted(self):
        cfg = _config("Goal: {{ task }}")
        result = build_iteration_context(cfg, 0)
        assert "Fix the auth bug" in result

    def test_iteration_idx_substituted(self):
        cfg = _config("Iter: {{ iteration_idx }}")
        result = build_iteration_context(cfg, 3)
        assert "Iter: 3" in result

    def test_feedback_is_none_by_default(self):
        cfg = _config("{% if feedback %}FEEDBACK{% else %}NO_FEEDBACK{% endif %}")
        result = build_iteration_context(cfg, 0)
        assert result.strip() == "NO_FEEDBACK"

    def test_no_extra_whitespace_on_simple_template(self):
        cfg = _config("{{ task }}")
        result = build_iteration_context(cfg, 0)
        assert result == "Fix the auth bug"

    def test_unknown_variable_raises(self):
        from jinja2 import UndefinedError
        cfg = _config("{{ nonexistent_var }}")
        with pytest.raises(UndefinedError):
            build_iteration_context(cfg, 0)


# ---------------------------------------------------------------------------
# Rendering with feedback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildIterationContextWithFeedback:
    def test_feedback_summary_rendered(self):
        cfg = _config(
            "Goal: {{ task }}\n{% if feedback %}Feedback: {{ feedback.summary }}{% endif %}"
        )
        fb = Feedback(iteration_idx=0, summary="Tests failed")
        result = build_iteration_context(cfg, 1, feedback=fb)
        assert "Feedback: Tests failed" in result

    def test_feedback_none_suppresses_block(self):
        cfg = _config(
            "Goal: {{ task }}\n{% if feedback %}Feedback: {{ feedback.summary }}{% endif %}"
        )
        result = build_iteration_context(cfg, 1, feedback=None)
        assert "Feedback:" not in result

    def test_feedback_fields_accessible(self):
        cfg = _config(
            "Causes: {% for c in feedback.root_causes %}{{ c }}{% endfor %}"
        )
        fb = Feedback(iteration_idx=0, summary="x", root_causes=["null ptr", "missing import"])
        result = build_iteration_context(cfg, 1, feedback=fb)
        assert "null ptr" in result
        assert "missing import" in result


# ---------------------------------------------------------------------------
# Rendering with reference_inputs
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildIterationContextReferenceInputs:
    def test_reference_inputs_available(self):
        inputs = [
            ReferenceInput(name="spec", value="./spec.md", is_path=True),
            ReferenceInput(name="style", value="snake_case"),
        ]
        cfg = _config(
            "{% for r in reference_inputs %}{{ r.name }}={{ r.value }} {% endfor %}",
            reference_inputs=inputs,
        )
        result = build_iteration_context(cfg, 0)
        assert "spec=./spec.md" in result
        assert "style=snake_case" in result

    def test_empty_reference_inputs(self):
        cfg = _config(
            "inputs: {{ reference_inputs | length }}",
            reference_inputs=[],
        )
        result = build_iteration_context(cfg, 0)
        assert result == "inputs: 0"

    def test_is_path_flag_accessible(self):
        inputs = [ReferenceInput(name="f", value="x.md", is_path=True)]
        cfg = _config("{{ reference_inputs[0].is_path }}", reference_inputs=inputs)
        result = build_iteration_context(cfg, 0)
        assert result.strip() == "True"
