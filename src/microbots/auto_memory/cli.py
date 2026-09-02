"""Command-line entry point for the auto-memory train/eval loop.

Two modes, selected by ``--task``:

- ``--task <name>`` given: run the full train <-> eval loop for that
  task.
- ``--task`` omitted: train only, no eval task, with empty feedback.

Both modes are dispatched via ``orchestrator.run``.
"""

import argparse
import logging
from pathlib import Path

from microbots.auto_memory.orchestrator import run
from microbots.auto_memory.task_registry import TASK_REGISTRY, discover_tasks
from microbots.auto_memory.workdir import load_config, require_workdir, resolve_workdir

logger = logging.getLogger(__name__)

# Import every task module so their @register_task decorators fire.
discover_tasks()

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the CLI's top-level args.

    Task-specific values (e.g. an eval task's instance ID) are not
    parsed here; they come from the workdir's config file instead.

    Parameters
    ----------
    argv : list[str] | None
        Args to parse. Defaults to ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    argparse.Namespace
        The parsed args.
    """
    parser = argparse.ArgumentParser(description="Run the auto-memory train/eval loop.")
    parser.add_argument("--model", required=True, help='Model, e.g. "azure-openai/gpt-5.5".')
    parser.add_argument(
        "--workdir",
        help="Directory holding this run's files (repo clone, logs, memory, "
        "config). Defaults to './workdir' relative to the current directory.",
    )
    parser.add_argument(
        "--task",
        choices=sorted(TASK_REGISTRY),
        help="Eval task to run. Omit to only run training, with no eval task.",
    )
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--training-iterations", type=int, default=10)

    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> None:
    """CLI entry point: run training only, or the full train/eval loop.

    Parameters
    ----------
    argv : list[str] | None
        Args to parse. Defaults to ``sys.argv[1:]`` when ``None``.
    """
    args = parse_args(argv)

    workdir = Path(args.workdir) if args.workdir else resolve_workdir()
    require_workdir(workdir)

    config = load_config(workdir)
    tasks = (
        TASK_REGISTRY[args.task].from_config(config.get("task_args", {}))
        if args.task
        else [None]
    )
    for task in tasks:
        result = run(
            workdir=workdir,
            model=args.model,
            task=task,
            max_rounds=args.max_rounds,
            training_iterations=args.training_iterations,
            config=config,
        )
        if result is not None:
            logger.info(
                "task=%s passed=%s rounds_run=%d", args.task, result.passed, result.rounds_run
            )

if __name__ == "__main__":
    main()
