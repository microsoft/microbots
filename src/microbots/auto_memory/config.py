"""Task configuration dataclass and YAML loader for auto_memory runs."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.data_models import CallbackSpec, ReferenceInput
from microbots.constants import ModelProvider

logger = getLogger(__name__)

DEFAULT_PROMPT_TEMPLATE = """\
{{ task }}
{% if reference_inputs %}
Reference inputs:
{% for item in reference_inputs %}- {{ item.name }}: {{ item.value }}
{% endfor %}{% endif %}
{% if feedback %}
The previous attempt did not pass validation. Address this feedback:
{{ feedback.summary }}
{% if feedback.root_causes %}
Root causes:
{% for cause in feedback.root_causes %}- {{ cause }}
{% endfor %}{% endif %}
{% if feedback.validator_failures %}
Validator failures:
{% for failure in feedback.validator_failures %}- {{ failure }}
{% endfor %}{% endif %}
{% if feedback.suggested_actions %}
Suggested actions:
{% for action in feedback.suggested_actions %}- {{ action }}
{% endfor %}{% endif %}
{% endif %}"""


@dataclass
class TaskConfig:
    """All configuration for one auto_memory run, loaded from a YAML file."""

    # --- required ---
    task_definition: str
    callbacks: list[CallbackSpec]

    # --- optional with defaults ---
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE
    model: str | None = None
    workdir: str = ".auto-memory"
    reference_inputs: list[ReferenceInput] = field(default_factory=list)
    output_format: str = "dir"          # "file" | "dir" | "stdout"
    output_path: str = "candidate"      # relative to iteration dir
    max_iterations: int = 5
    timeout_min: int = 60
    per_iteration_timeout: int = 600    # seconds

    # --- analyzer (LogAnalysisBot) settings ---
    analyzer_model: str = "azure-openai/gpt-5"
    analyzer_max_iterations: int = 20
    analyzer_timeout_s: int = 300

    # -----------------------------------------------------------------------

    @classmethod
    def load_from_yaml(cls, path: str) -> "TaskConfig":
        """Parse a task YAML file into a TaskConfig.

        Parameters
        ----------
        path : str
            Filesystem path to the YAML configuration file.

        Returns
        -------
        TaskConfig
            Fully validated configuration object.

        Raises
        ------
        ConfigError
            If the file is not found, not valid YAML, or missing required
            fields.
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise ConfigError(f"Task config file not found: {path}")

        try:
            with yaml_path.open() as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse YAML from {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"Expected a YAML mapping at the top level in {path}")

        legacy_runner_fields = {"runner", "runner_params"}.intersection(data)
        if legacy_runner_fields:
            fields = ", ".join(sorted(legacy_runner_fields))
            raise ConfigError(
                f"YAML runner configuration ({fields}) is not supported; "
                "construct a custom AgentRunner in Python and pass it as "
                "run_from_yaml(..., agent_runner=runner)"
            )

        # required fields
        for required in ("task_definition",):
            if required not in data:
                raise ConfigError(f"Missing required field '{required}' in {path}")

        # reference_inputs
        raw_inputs = data.get("reference_inputs", [])
        reference_inputs = [
            ReferenceInput(
                name=item["name"],
                value=item["value"],
                is_path=bool(item.get("is_path", False)),
            )
            for item in (raw_inputs or [])
        ]

        # callbacks
        raw_callbacks = data.get("callbacks", [])
        callbacks = [
            CallbackSpec(
                name=cb["name"],
                command=cb["command"],
                timeout_s=int(cb.get("timeout_s", 120)),
                expected_return_code=int(cb.get("expected_return_code", 0)),
            )
            for cb in (raw_callbacks or [])
        ]

        config = cls(
            task_definition=data["task_definition"].strip(),
            callbacks=callbacks,
            prompt_template=data.get("prompt_template", DEFAULT_PROMPT_TEMPLATE),
            model=(str(data["model"]) if data.get("model") is not None else None),
            workdir=str(data.get("workdir", ".auto-memory")),
            reference_inputs=reference_inputs,
            output_format=data.get("output_format", "dir"),
            output_path=data.get("output_path", "candidate"),
            max_iterations=int(data.get("max_iterations", 5)),
            timeout_min=int(data.get("timeout_min", 60)),
            per_iteration_timeout=int(data.get("per_iteration_timeout", 600)),
            analyzer_model=str(data.get("analyzer_model", "azure-openai/gpt-5")),
            analyzer_max_iterations=int(data.get("analyzer_max_iterations", 20)),
            analyzer_timeout_s=int(data.get("analyzer_timeout_s", 300)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate the config.

        Raises:
            ConfigError: on any invalid field.
        """
        if not self.task_definition:
            raise ConfigError("'task_definition' must not be empty")

        if not self.prompt_template:
            raise ConfigError("'prompt_template' must not be empty")

        if self.model is not None:
            self._validate_model(self.model, "model")

        if not self.workdir.strip():
            raise ConfigError("'workdir' must not be empty")

        if self.max_iterations < 1:
            raise ConfigError(f"'max_iterations' must be >= 1, got {self.max_iterations}")

        if self.timeout_min < 1:
            raise ConfigError(f"'timeout_min' must be >= 1, got {self.timeout_min}")

        if self.per_iteration_timeout < 1:
            raise ConfigError(
                f"'per_iteration_timeout' must be >= 1, got {self.per_iteration_timeout}"
            )

        self._validate_model(self.analyzer_model, "analyzer_model")

        if self.analyzer_max_iterations < 1:
            raise ConfigError(
                f"'analyzer_max_iterations' must be >= 1, got {self.analyzer_max_iterations}"
            )

        if self.analyzer_timeout_s < 1:
            raise ConfigError(
                f"'analyzer_timeout_s' must be >= 1, got {self.analyzer_timeout_s}"
            )

        if self.output_format not in ("file", "dir", "stdout"):
            raise ConfigError(
                f"'output_format' must be 'file', 'dir', or 'stdout', got '{self.output_format}'"
            )

        if Path(self.output_path).is_absolute():
            raise ConfigError(
                f"'output_path' must be a relative path, got '{self.output_path}'"
            )

        if ".." in Path(self.output_path).parts:
            raise ConfigError(
                f"'output_path' must not contain '..', got '{self.output_path}'"
            )

        if not self.callbacks:
            raise ConfigError("'callbacks' must contain at least one entry")

        for cb in self.callbacks:
            if not cb.name:
                raise ConfigError("Each callback must have a non-empty 'name'")
            if not cb.command:
                raise ConfigError(
                    f"Callback '{cb.name}' must have a non-empty 'command'"
                )

        for ri in self.reference_inputs:
            if not ri.name:
                raise ConfigError("Each reference_input must have a non-empty 'name'")
            if not ri.value:
                raise ConfigError(
                    f"reference_input '{ri.name}' must have a non-empty 'value'"
                )

    @staticmethod
    def _validate_model(model: str, field_name: str) -> None:
        """Validate a model identifier using the framework provider contract.

        Parameters
        ----------
        model : str
            Model identifier in ``<provider>/<model_name>`` form.
        field_name : str
            Configuration field name used in validation errors.
        """
        if not model:
            raise ConfigError(f"'{field_name}' must not be empty")
        if model.count("/") != 1:
            raise ConfigError(
                f"'{field_name}' must be in the format '<provider>/<model_name>', "
                f"got '{model}'"
            )
        provider = model.split("/", 1)[0]
        supported = [e.value for e in ModelProvider]
        if provider not in supported:
            raise ConfigError(
                f"'{field_name}' has unsupported provider '{provider}'; "
                f"expected one of {supported}"
            )
