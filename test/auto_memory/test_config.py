import textwrap
import pytest
from pathlib import Path

from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.errors import ConfigError


MINIMAL_YAML = textwrap.dedent("""\
    task_definition: Fix the bug
    prompt_template: "Goal: {{ task }}"
    callbacks:
      - name: tests
        command: pytest "$CANDIDATE"
""")

FULL_YAML = textwrap.dedent("""\
    task_definition: Fix the auth bug
    prompt_template: |
      Goal: {{ task }}
      {% if feedback %}Feedback: {{ feedback.summary }}{% endif %}

    reference_inputs:
      - name: spec
        value: ./spec.md
        is_path: true
      - name: style
        value: snake_case

    output_format: dir
    output_path: candidate
    max_iterations: 3
    timeout_min: 30
    per_iteration_timeout: 300

    callbacks:
      - name: unit_tests
        command: pytest "$CANDIDATE"
        timeout_s: 180
      - name: lint
        command: ruff check "$CANDIDATE"
        expected_return_code: 0
""")


@pytest.fixture
def tmp_yaml(tmp_path):
    """Helper that writes content to a temp file and returns its path."""
    def _write(content: str) -> str:
        p = tmp_path / "task.yml"
        p.write_text(content)
        return str(p)
    return _write


@pytest.mark.unit
class TestLoadFromYaml:
    def test_minimal_valid(self, tmp_yaml):
        cfg = TaskConfig.load_from_yaml(tmp_yaml(MINIMAL_YAML))
        assert cfg.task_definition == "Fix the bug"
        assert "{{ task }}" in cfg.prompt_template

    def test_full_yaml(self, tmp_yaml):
        cfg = TaskConfig.load_from_yaml(tmp_yaml(FULL_YAML))
        assert cfg.max_iterations == 3
        assert cfg.timeout_min == 30
        assert cfg.per_iteration_timeout == 300
        assert len(cfg.reference_inputs) == 2
        assert len(cfg.callbacks) == 2

    def test_reference_inputs_parsed(self, tmp_yaml):
        cfg = TaskConfig.load_from_yaml(tmp_yaml(FULL_YAML))
        spec = cfg.reference_inputs[0]
        assert spec.name == "spec"
        assert spec.value == "./spec.md"
        assert spec.is_path is True
        style = cfg.reference_inputs[1]
        assert style.is_path is False

    def test_callbacks_parsed(self, tmp_yaml):
        cfg = TaskConfig.load_from_yaml(tmp_yaml(FULL_YAML))
        cb = cfg.callbacks[0]
        assert cb.name == "unit_tests"
        assert cb.timeout_s == 180
        assert cb.expected_return_code == 0

    def test_defaults_applied(self, tmp_yaml):
        cfg = TaskConfig.load_from_yaml(tmp_yaml(MINIMAL_YAML))
        assert cfg.max_iterations == 5
        assert cfg.timeout_min == 60
        assert cfg.per_iteration_timeout == 600
        assert cfg.output_format == "dir"
        assert cfg.output_path == "candidate"
        assert cfg.reference_inputs == []

    def test_missing_callbacks(self, tmp_yaml):
        yaml = textwrap.dedent("""\
            task_definition: Fix the bug
            prompt_template: "Goal: {{ task }}"
        """)
        with pytest.raises(ConfigError, match="callbacks"):
            TaskConfig.load_from_yaml(tmp_yaml(yaml))

    def test_file_not_found(self):
        with pytest.raises(ConfigError, match="not found"):
            TaskConfig.load_from_yaml("/nonexistent/path/task.yml")

    def test_invalid_yaml(self, tmp_yaml):
        with pytest.raises(ConfigError, match="Failed to parse YAML"):
            TaskConfig.load_from_yaml(tmp_yaml("}{invalid yaml}{"))

    def test_missing_task_definition(self, tmp_yaml):
        with pytest.raises(ConfigError, match="task_definition"):
            TaskConfig.load_from_yaml(tmp_yaml("prompt_template: hello"))

    def test_missing_prompt_template(self, tmp_yaml):
        with pytest.raises(ConfigError, match="prompt_template"):
            TaskConfig.load_from_yaml(tmp_yaml("task_definition: hello"))

    def test_not_a_mapping(self, tmp_yaml):
        with pytest.raises(ConfigError, match="mapping"):
            TaskConfig.load_from_yaml(tmp_yaml("- item1\n- item2\n"))


@pytest.mark.unit
class TestValidate:
    def _base(self) -> TaskConfig:
        from microbots.auto_memory.data_models import CallbackSpec
        return TaskConfig(
            task_definition="Fix the bug",
            prompt_template="Goal: {{ task }}",
            callbacks=[CallbackSpec(name="tests", command="pytest")],
        )

    def test_valid_passes(self):
        self._base().validate()  # should not raise

    def test_empty_task_definition(self):
        cfg = self._base()
        cfg.task_definition = ""
        with pytest.raises(ConfigError, match="task_definition"):
            cfg.validate()

    def test_empty_prompt_template(self):
        cfg = self._base()
        cfg.prompt_template = ""
        with pytest.raises(ConfigError, match="prompt_template"):
            cfg.validate()

    def test_max_iterations_zero(self):
        cfg = self._base()
        cfg.max_iterations = 0
        with pytest.raises(ConfigError, match="max_iterations"):
            cfg.validate()

    def test_timeout_min_zero(self):
        cfg = self._base()
        cfg.timeout_min = 0
        with pytest.raises(ConfigError, match="timeout_min"):
            cfg.validate()

    def test_per_iteration_timeout_zero(self):
        cfg = self._base()
        cfg.per_iteration_timeout = 0
        with pytest.raises(ConfigError, match="per_iteration_timeout"):
            cfg.validate()

    def test_invalid_output_format(self):
        cfg = self._base()
        cfg.output_format = "json"
        with pytest.raises(ConfigError, match="output_format"):
            cfg.validate()

    def test_absolute_output_path(self):
        cfg = self._base()
        cfg.output_path = "/absolute/path"
        with pytest.raises(ConfigError, match="output_path"):
            cfg.validate()

    def test_callback_empty_name(self):
        from microbots.auto_memory.data_models import CallbackSpec
        cfg = self._base()
        cfg.callbacks = [CallbackSpec(name="", command="pytest")]
        with pytest.raises(ConfigError, match="name"):
            cfg.validate()

    def test_callback_empty_command(self):
        from microbots.auto_memory.data_models import CallbackSpec
        cfg = self._base()
        cfg.callbacks = [CallbackSpec(name="tests", command="")]
        with pytest.raises(ConfigError, match="command"):
            cfg.validate()

    def test_reference_input_empty_name(self):
        from microbots.auto_memory.data_models import ReferenceInput
        cfg = self._base()
        cfg.reference_inputs = [ReferenceInput(name="", value="val")]
        with pytest.raises(ConfigError, match="name"):
            cfg.validate()

    def test_reference_input_empty_value(self):
        from microbots.auto_memory.data_models import ReferenceInput
        cfg = self._base()
        cfg.reference_inputs = [ReferenceInput(name="spec", value="")]
        with pytest.raises(ConfigError, match="value"):
            cfg.validate()

    def test_empty_callbacks_list(self):
        cfg = self._base()
        cfg.callbacks = []
        with pytest.raises(ConfigError, match="callbacks"):
            cfg.validate()
