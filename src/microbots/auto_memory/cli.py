"""User-facing entry point that wires every auto_memory component."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.callbacks import CallbackRunner, ShellCallbackRunner
from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.orchestrator import RunSummary, TrainingLoopOrchestrator
from microbots.auto_memory.runners.base import AgentRunner
from microbots.auto_memory.runners.writing_bot_runner import WritingBotRunner
from microbots.auto_memory.workspace import WorkspaceManager

logger = getLogger(__name__)


def run_from_yaml(
    yaml_path: str | Path,
    workdir: str | Path | None = None,
    run_id: str | None = None,
    *,
    model: str | None = None,
    external_memory_dir: str | Path | None = None,
    agent_runner: AgentRunner | None = None,
    callback_runner: CallbackRunner | None = None,
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
    workdir : str | Path | None, optional
        Parent directory that holds the ``runs/`` tree. Defaults to the YAML
        ``workdir`` value, resolved relative to the YAML file's directory.
    run_id : str | None, optional
        Identifier for this run.  When ``None`` a UTC timestamp plus a short
        random suffix of the form ``run-YYYYMMDD-HHMMSS-ffffff-<rand>`` is
        generated to avoid collisions.
    model : str | None, optional
        Model identifier forwarded to the configured runner. Overrides the
        YAML ``model`` value when provided.
    external_memory_dir : str | Path | None, optional
        If provided, mount this pre-populated directory as the run's memory
        directory instead of creating ``<run_dir>/memory/``. Useful for
        reusing notes produced by the training loop. Non-feedback files
        inside it are never modified.
    agent_runner : AgentRunner | None, optional
        User-constructed runner for custom agent behavior. Defaults to a
        :class:`WritingBotRunner` configured with the resolved model.
    callback_runner : CallbackRunner | None, optional
        User-provided callback runner. Defaults to :class:`ShellCallbackRunner`,
        which executes the callback commands declared in the task YAML.

    Returns
    -------
    RunSummary
        Summary of the completed run.
    """
    yaml_path = Path(yaml_path)
    config = TaskConfig.load_from_yaml(str(yaml_path))

    resolved_model = model or config.model
    if agent_runner is None and resolved_model is None:
        raise ConfigError(
            "A model is required; set 'model' in the task YAML or pass model=..."
        )

    if workdir is None:
        configured_workdir = Path(config.workdir)
        workdir = (
            configured_workdir
            if configured_workdir.is_absolute()
            else yaml_path.resolve().parent / configured_workdir
        )

    if run_id is None:
        run_id = _generate_run_id()

    run_dir = Path(workdir) / "runs" / run_id
    logger.info("auto_memory: starting run %s at %s", run_id, run_dir)

    if agent_runner is None:
        assert resolved_model is not None
        agent_runner = WritingBotRunner(model=resolved_model)

    # Custom runners must explicitly implement the framework extension point.
    if not isinstance(agent_runner, AgentRunner):
        raise ConfigError(
            "The provided agent_runner must inherit AgentRunner and implement "
            "run(ctx, timeout_s)"
        )
    logger.info("auto_memory: using runner %s", type(agent_runner).__name__)

    workspace = WorkspaceManager(
        run_dir=run_dir,
        external_memory_dir=Path(external_memory_dir) if external_memory_dir else None,
    )
    if callback_runner is None:
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


def main(argv: list[str] | None = None) -> int:
    """Run an auto-memory task from a YAML file.

    Parameters
    ----------
    argv : list[str] | None, optional
        Arguments to parse. Uses :data:`sys.argv` when omitted.

    Returns
    -------
    int
        Process exit code, with zero indicating a completed run.
    """
    parser = argparse.ArgumentParser(
        prog="python -m microbots.auto_memory",
        description="Run an iterative auto-memory feedback loop.",
    )
    parser.add_argument("yaml_path", type=Path, help="Task YAML file.")
    parser.add_argument("--model", help="Override the model declared in YAML.")
    parser.add_argument(
        "--workdir", type=Path, help="Override the work directory declared in YAML."
    )
    parser.add_argument("--run-id", help="Use a fixed run identifier.")
    parser.add_argument(
        "--external-memory-dir",
        type=Path,
        help="Reuse an existing memory directory.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_from_yaml(
            args.yaml_path,
            workdir=args.workdir,
            run_id=args.run_id,
            model=args.model,
            external_memory_dir=args.external_memory_dir,
        )
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    print(
        f"auto-memory {summary.final_status.value}: "
        f"iterations={summary.iterations_run} elapsed={summary.elapsed_s:.1f}s"
    )
    if summary.error_message:
        print(f"last error: {summary.error_message}", file=sys.stderr)
    return 0
