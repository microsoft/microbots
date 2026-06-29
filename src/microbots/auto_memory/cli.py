"""User-facing entry point that wires every auto_memory component."""

from __future__ import annotations

from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.callbacks import ShellCallbackRunner
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.orchestrator import RunSummary, TrainingLoopOrchestrator
from microbots.auto_memory.runners.writing_bot_runner import WritingBotRunner
from microbots.auto_memory.workspace import WorkspaceManager

logger = getLogger(__name__)


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
        Identifier for this run.  When ``None`` a UTC timestamp of the form
        ``run-YYYYMMDD-HHMMSS-ffffff`` is generated.
    model : str
        Model identifier forwarded to :class:`WritingBotRunner` (required,
        keyword-only — e.g. ``"azure/gpt-4o"``).

    Returns
    -------
    RunSummary
        Summary of the completed run.
    """
    config = TaskConfig.load_from_yaml(str(yaml_path))

    if run_id is None:
        run_id = _generate_run_id()

    run_dir = Path(workdir) / "runs" / run_id
    logger.info("auto_memory: starting run %s at %s", run_id, run_dir)

    workspace = WorkspaceManager(run_dir=run_dir)
    agent_runner = WritingBotRunner(model=model)
    callback_runner = ShellCallbackRunner()

    orchestrator = TrainingLoopOrchestrator(
        config=config,
        agent_runner=agent_runner,
        callback_runner=callback_runner,
        workspace=workspace,
    )

    return orchestrator.run()


def _generate_run_id() -> str:
    """Return a UTC-timestamp-based run identifier.

    Returns
    -------
    str
        Identifier of the form ``run-YYYYMMDD-HHMMSS-ffffff`` using the
        current UTC time.
    """
    return "run-" + datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
