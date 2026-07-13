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


@dataclass
class TaskConfig:
    """All configuration for one auto_memory run, loaded from a YAML file."""

    # --- required ---
    task_definition: str
    prompt_template: str
    callbacks: list[CallbackSpec]

    # --- optional with defaults ---
    reference_inputs: list[ReferenceInput] = field(default_factory=list)
    output_format: str = "dir"          # "file" | "dir" | "stdout"
    output_path: str = "candidate"      # relative to iteration dir
    max_iterations: int = 5
    timeout_min: int = 60
    per_iteration_timeout: int = 600    # seconds

    # --- analyzer (LogAnalysisBot) settings ---
    analyzer_model: str = "azure-openai/gpt-4o"
    analyzer_max_iterations: int = 20
    analyzer_timeout_s: int = 300

    # --- runner selection ---
    # Either a dotted import path ("pkg.module.ClassName") or a file-path form
    # ("path/to/file.py:ClassName") resolved relative to the task YAML's dir.
    # Defaults to the built-in WritingBotRunner so existing configs are
    # unaffected. Extra keyword arguments for the runner's constructor go in
    # runner_params (model is always injected separately by the CLI).
    runner: str = "microbots.auto_memory.runners.writing_bot_runner.WritingBotRunner"
    runner_params: dict = field(default_factory=dict)

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

        # required fields
        for required in ("task_definition", "prompt_template"):
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
            prompt_template=data["prompt_template"],
            callbacks=callbacks,
            reference_inputs=reference_inputs,
            output_format=data.get("output_format", "dir"),
            output_path=data.get("output_path", "candidate"),
            max_iterations=int(data.get("max_iterations", 5)),
            timeout_min=int(data.get("timeout_min", 60)),
            per_iteration_timeout=int(data.get("per_iteration_timeout", 600)),
            analyzer_model=str(data.get("analyzer_model", "azure-openai/gpt-4o")),
            analyzer_max_iterations=int(data.get("analyzer_max_iterations", 20)),
            analyzer_timeout_s=int(data.get("analyzer_timeout_s", 300)),
            runner=str(
                data.get(
                    "runner",
                    "microbots.auto_memory.runners.writing_bot_runner.WritingBotRunner",
                )
            ),
            # Pass through as-is (no dict() coercion) so a non-mapping value
            # reaches validate() and produces a clear ConfigError instead of a
            # cryptic ValueError/TypeError from dict().
            runner_params=data.get("runner_params", {}) or {},
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

        if self.max_iterations < 1:
            raise ConfigError(f"'max_iterations' must be >= 1, got {self.max_iterations}")

        if self.timeout_min < 1:
            raise ConfigError(f"'timeout_min' must be >= 1, got {self.timeout_min}")

        if self.per_iteration_timeout < 1:
            raise ConfigError(
                f"'per_iteration_timeout' must be >= 1, got {self.per_iteration_timeout}"
            )

        if not self.analyzer_model:
            raise ConfigError("'analyzer_model' must not be empty")

        # Mirror MicroBot._validate_model_and_provider so we fail fast at
        # config load time instead of deferring to a runtime ValueError
        # when LogAnalysisBot is instantiated.
        if self.analyzer_model.count("/") != 1:
            raise ConfigError(
                f"'analyzer_model' must be in the format '<provider>/<model_name>', "
                f"got '{self.analyzer_model}'"
            )
        provider = self.analyzer_model.split("/", 1)[0]
        supported = [e.value for e in ModelProvider]
        if provider not in supported:
            raise ConfigError(
                f"'analyzer_model' has unsupported provider '{provider}'; "
                f"expected one of {supported}"
            )

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

        if not self.runner or not self.runner.strip():
            raise ConfigError("'runner' must not be empty")

        if not isinstance(self.runner_params, dict):
            raise ConfigError(
                f"'runner_params' must be a mapping, got {type(self.runner_params).__name__}"
            )

        if "model" in self.runner_params:
            raise ConfigError(
                "'runner_params' must not contain 'model'; it is injected "
                "automatically by the CLI"
            )
