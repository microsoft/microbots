"""Configuration for a training run.

Attributes
----------
agents_md_path
    Path to the ``AGENTS.md`` file used as the base prompt for every
    iteration.
source
    :class:`~microbots.auto_memory.training.training_source.TrainingSource` describing
    where the directory the agent should learn from comes from. It can be
    an existing local directory (``type: path``) or a git repository that
    is cloned before the run starts (``type: git``). The resolved local
    directory is mounted into the bot's sandbox as the working directory.

    In YAML the shape is a nested mapping::

        source:
          type: path
          path: /some/dir

        # or

        source:
          type: git
          url: https://github.com/foo/bar.git
          ref: main            # optional
          cache_dir: /some/dir # optional; defaults to <workdir>/source

    Legacy top-level ``source_path: <dir>`` is still accepted and normalised
    into ``TrainingSource(type='path', path=...)``. If the legacy value looks
    like a URL it is treated as ``type='git'``.
memory_dir
    Host-side directory that backs the agent's ``/memories/`` tree. Notes
    persist here across iterations and across runs (see ``reset_memory``).
model
    Model identifier forwarded to the runner (e.g. ``"azure-openai/gpt-4o"``).
iterations
    Number of training iterations to execute back-to-back. Memory persists
    across iterations, so each iteration builds on the previous one.
per_iteration_timeout
    Wall-clock cap for one iteration, in seconds.
total_timeout_min
    Wall-clock cap for the whole run, in minutes. ``0`` disables it.
max_bot_steps
    ``max_iterations`` forwarded to the underlying bot (its internal
    tool-loop cap, not the training loop's iteration count).
reset_memory
    When ``True``, wipe ``memory_dir`` before the first iteration. When
    ``False`` (default), existing notes are preserved.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.training_source import TrainingSource
from microbots.constants import ModelProvider

logger = getLogger(__name__)

_DEFAULT_AGENTS_MD = Path(__file__).parent / "training_instructions.md"


@dataclass
class TrainingConfig:
    """All configuration for one training run."""

    source: TrainingSource
    memory_dir: Path
    model: str
    agents_md_path: Path = _DEFAULT_AGENTS_MD
    iterations: int = 3
    per_iteration_timeout: int = 900
    total_timeout_min: int = 0
    max_bot_steps: int = 40
    reset_memory: bool = False

    # ------------------------------------------------------------------
    # Back-compat convenience

    @property
    def source_path(self) -> Path | None:
        """Best-effort local source path.

        For ``type='path'`` this is the configured directory. For
        ``type='git'`` this is ``None`` until :meth:`TrainingSource.materialize`
        has been called (typically by the training loop at run start).

        Returns
        -------
        Path | None
            Configured or materialized local source path, when available.
        """
        return self.source.path

    # ------------------------------------------------------------------

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "TrainingConfig":
        """Parse a training YAML file into a :class:`TrainingConfig`.

        The YAML file must provide ``memory_dir``, ``model``, and either a
        nested ``source:`` mapping or a legacy ``source_path`` string. All
        other keys map 1:1 to the dataclass fields. Filesystem paths
        (``memory_dir``, ``agents_md_path``, and any paths inside
        ``source``) are resolved relative to the YAML file's directory when
        written as relative paths.

        Parameters
        ----------
        path : str | Path
            Filesystem path to the YAML configuration.

        Returns
        -------
        TrainingConfig
            Fully validated configuration.

        Raises
        ------
        ConfigError
            If the file is missing, unparseable, or has invalid fields.
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise ConfigError(f"Training config file not found: {path}")

        try:
            with yaml_path.open() as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse YAML from {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"Expected a YAML mapping at the top of {path}")

        for required in ("memory_dir", "model"):
            if required not in data:
                raise ConfigError(f"Missing required field '{required}' in {path}")

        if "source" not in data and "source_path" not in data:
            raise ConfigError(
                f"Missing source: provide either 'source:' (mapping) or "
                f"legacy 'source_path:' in {path}"
            )

        base = yaml_path.resolve().parent

        def _resolve(p: str | Path) -> Path:
            """Resolve a configured path relative to the YAML directory.

            Parameters
            ----------
            p : str | Path
                Configured filesystem path.

            Returns
            -------
            Path
                Absolute path, or the unchanged absolute input path.
            """
            p = Path(p)
            return p if p.is_absolute() else (base / p).resolve()

        if "source" in data:
            source = TrainingSource.from_mapping(data["source"], base_dir=base)
        else:
            source = TrainingSource.from_legacy_source_path(
                data["source_path"], base_dir=base
            )

        agents_md_raw = data.get("agents_md_path")
        agents_md = _resolve(agents_md_raw) if agents_md_raw else _DEFAULT_AGENTS_MD

        config = cls(
            source=source,
            memory_dir=_resolve(data["memory_dir"]),
            model=str(data["model"]),
            agents_md_path=agents_md,
            iterations=int(data.get("iterations", 3)),
            per_iteration_timeout=int(data.get("per_iteration_timeout", 900)),
            total_timeout_min=int(data.get("total_timeout_min", 0)),
            max_bot_steps=int(data.get("max_bot_steps", 40)),
            reset_memory=bool(data.get("reset_memory", False)),
        )
        config.validate()
        return config

    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate every field. Raises :class:`ConfigError` on any issue."""
        self.source.validate()

        if not self.agents_md_path.exists() or not self.agents_md_path.is_file():
            raise ConfigError(
                f"'agents_md_path' must point to an existing file, got "
                f"{self.agents_md_path}"
            )

        if not self.model:
            raise ConfigError("'model' must not be empty")
        if self.model.count("/") != 1:
            raise ConfigError(
                f"'model' must be in the form '<provider>/<name>', got '{self.model}'"
            )
        provider = self.model.split("/", 1)[0]
        supported = [e.value for e in ModelProvider]
        if provider not in supported:
            raise ConfigError(
                f"'model' has unsupported provider '{provider}'; "
                f"expected one of {supported}"
            )

        if self.iterations < 1:
            raise ConfigError(f"'iterations' must be >= 1, got {self.iterations}")

        if self.per_iteration_timeout < 1:
            raise ConfigError(
                f"'per_iteration_timeout' must be >= 1, got {self.per_iteration_timeout}"
            )

        if self.total_timeout_min < 0:
            raise ConfigError(
                f"'total_timeout_min' must be >= 0, got {self.total_timeout_min}"
            )

        if self.max_bot_steps < 1:
            raise ConfigError(
                f"'max_bot_steps' must be >= 1, got {self.max_bot_steps}"
            )

    # ------------------------------------------------------------------

    def read_agents_md(self) -> str:
        """Read the configured ``AGENTS.md`` file.

        Returns
        -------
        str
            Contents of the training instructions file.
        """
        return self.agents_md_path.read_text(encoding="utf-8")
