"""User-facing entry point that wires every auto_memory component."""

from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import Callable

from microbots.auto_memory.callbacks import ShellCallbackRunner
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.orchestrator import RunSummary, TrainingLoopOrchestrator
from microbots.auto_memory.runners.base import AgentRunner
from microbots.auto_memory.workspace import WorkspaceManager

logger = getLogger(__name__)


def _load_runner_class(runner_spec: str, base_dir: Path) -> Callable[..., AgentRunner]:
    """Resolve a runner class from a task config ``runner`` string.

    Two forms are supported:

    * **Dotted import path** — ``"pkg.module.ClassName"``. Imported via the
      normal import system; the module must be importable (installed package
      or on ``sys.path``).
    * **File path plus class** — ``"path/to/file.py:ClassName"``. Loaded
      directly from disk with :mod:`importlib.util`, so the runner can live
      outside the microbots package. Relative file paths are resolved against
      *base_dir* (the task YAML's directory).

    Parameters
    ----------
    runner_spec : str
        The ``runner`` value from the task configuration.
    base_dir : Path
        Directory used to resolve relative file paths (the task YAML's dir).

    Returns
    -------
    Callable[..., AgentRunner]
        The resolved runner factory — a class or any callable that accepts
        ``model=...`` plus ``runner_params`` and returns an
        :class:`~microbots.auto_memory.runners.base.AgentRunner`.

    Raises
    ------
    ConfigError
        If the spec is malformed, the module/file cannot be imported, the
        class is not found, or the resolved attribute is not callable.
    """
    if ":" in runner_spec:
        # File-path form: "<path>.py:<ClassName>"
        file_part, _, cls_name = runner_spec.rpartition(":")
        if not file_part or not cls_name:
            raise ConfigError(
                f"Invalid runner spec '{runner_spec}'; expected 'path/to/file.py:ClassName'"
            )
        file_path = Path(file_part)
        if not file_path.is_absolute():
            file_path = (base_dir / file_path).resolve()
        if not file_path.is_file():
            raise ConfigError(f"Runner file not found: {file_path}")

        module_spec = importlib.util.spec_from_file_location(
            "_microbots_user_runner", file_path
        )
        if module_spec is None or module_spec.loader is None:
            raise ConfigError(f"Cannot load runner module from {file_path}")
        module = importlib.util.module_from_spec(module_spec)
        try:
            module_spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - surface any import-time error
            raise ConfigError(
                f"Failed to import runner file {file_path}: {exc}"
            ) from exc
    else:
        # Dotted import path form: "pkg.module.ClassName"
        module_path, _, cls_name = runner_spec.rpartition(".")
        if not module_path or not cls_name:
            raise ConfigError(
                f"Invalid runner spec '{runner_spec}'; expected "
                f"'pkg.module.ClassName' or 'path/to/file.py:ClassName'"
            )
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ConfigError(
                f"Cannot import runner module '{module_path}': {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface import-time errors
            raise ConfigError(
                f"Failed to import runner module '{module_path}': {exc}"
            ) from exc

    try:
        runner_obj = getattr(module, cls_name)
    except AttributeError as exc:
        raise ConfigError(
            f"Runner class '{cls_name}' not found in '{runner_spec}'"
        ) from exc

    if not callable(runner_obj):
        raise ConfigError(
            f"Runner '{cls_name}' in '{runner_spec}' is not callable "
            f"(got {type(runner_obj).__name__}); expected a class or factory "
            f"that accepts model=... and returns an AgentRunner"
        )
    return runner_obj


def run_from_yaml(
    yaml_path: str | Path,
    workdir: str | Path,
    run_id: str | None = None,
    *,
    model: str,
) -> RunSummary:
    """Load a task YAML, wire all components, and run the iteration loop.

    The run is materialised under ``<workdir>/runs/<run_id>/`` with the
    following on-disk layout::

        <workdir>/runs/<run_id>/
        ├── memory/
        │   └── feedback.jsonl
        ├── iterations/
        │   ├── iter_00/
        │   │   ├── candidate/
        │   │   └── logs/
        │   └── ...
        └── run_meta.json

    Parameters
    ----------
    yaml_path : str | Path
        Path to the task configuration YAML file.
    workdir : str | Path
        Parent directory that holds the ``runs/`` tree.
    run_id : str | None, optional
        Identifier for this run.  When ``None`` a UTC timestamp plus a short
        random suffix of the form ``run-YYYYMMDD-HHMMSS-ffffff-<rand>`` is
        generated to avoid collisions.
    model : str
        Model identifier forwarded to the configured runner (required,
        keyword-only — e.g. ``"azure-openai/gpt-4o"``).

    Returns
    -------
    RunSummary
        Summary of the completed run.
    """
    yaml_path = Path(yaml_path)
    config = TaskConfig.load_from_yaml(str(yaml_path))

    if run_id is None:
        run_id = _generate_run_id()

    run_dir = Path(workdir) / "runs" / run_id
    logger.info("auto_memory: starting run %s at %s", run_id, run_dir)

    runner_cls = _load_runner_class(config.runner, base_dir=yaml_path.resolve().parent)
    try:
        agent_runner: AgentRunner = runner_cls(model=model, **config.runner_params)
    except Exception as exc:  # noqa: BLE001 - surface construction errors as config errors
        raise ConfigError(
            f"Failed to construct runner '{config.runner}' with "
            f"runner_params={config.runner_params!r}: {exc}"
        ) from exc

    # Structural check: the constructed object must satisfy the AgentRunner
    # protocol (i.e. expose a run() method). This only verifies method
    # presence, not its signature, but catches gross misconfigurations early
    # with a clear error instead of failing deep inside the orchestrator.
    if not isinstance(agent_runner, AgentRunner):
        raise ConfigError(
            f"Runner '{config.runner}' does not satisfy the AgentRunner "
            f"protocol; it must define run(ctx, timeout_s)"
        )
    logger.info("auto_memory: using runner %s", config.runner)

    workspace = WorkspaceManager(run_dir=run_dir)
    callback_runner = ShellCallbackRunner()

    orchestrator = TrainingLoopOrchestrator(
        config=config,
        agent_runner=agent_runner,
        callback_runner=callback_runner,
        workspace=workspace,
    )

    return orchestrator.run()


def _generate_run_id() -> str:
    """Return a unique UTC-timestamp-based run identifier.

    Returns
    -------
    str
        Identifier of the form ``run-YYYYMMDD-HHMMSS-ffffff-<rand>`` using
        the current UTC time plus an 8-character random suffix to guard
        against collisions on coarse-resolution clocks or concurrent starts.
    """
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"run-{timestamp}-{uuid.uuid4().hex[:8]}"
