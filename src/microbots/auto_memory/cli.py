"""Command-line entry point for the auto-memory train/eval loop.

Two modes, selected by ``--task``:

- ``--task <name>`` given: run the full train <-> eval loop for that
  task (via ``run_train_eval_loop``).
- ``--task`` omitted: train only, no eval task (via ``run_training_loop``,
  with empty feedback).
"""

import argparse
import logging

from microbots.auto_memory.orchestrator import run_train_eval_loop, run_training_loop
from microbots.auto_memory.task_registry import TASK_REGISTRY, discover_tasks

logger = logging.getLogger(__name__)

# Import every task module so their @register_task decorators fire.
discover_tasks()

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args, including task-specific args when ``--task`` is given.

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
    parser.add_argument("--repo", required=True, help="Absolute path to the repo.")
    parser.add_argument("--memory-dir", required=True, help="Directory for memory files.")
    parser.add_argument("--model", required=True, help='Model, e.g. "azure-openai/gpt-5.5".')
    parser.add_argument(
        "--task",
        choices=sorted(TASK_REGISTRY),
        help="Eval task to run. Omit to only run training, with no eval task.",
    )
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--training-iterations", type=int, default=1)

    # First pass just to discover --task, so we can register its
    # task-specific flags before the real parse.
    known_args, _ = parser.parse_known_args(argv)
    if known_args.task:
        TASK_REGISTRY[known_args.task].add_cli_args(parser)

    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> None:
    """CLI entry point: run training only, or the full train/eval loop.

    Parameters
    ----------
    argv : list[str] | None
        Args to parse. Defaults to ``sys.argv[1:]`` when ``None``.
    """
    args = parse_args(argv)

    if not args.task:
        run_training_loop(
            repo_path=args.repo,
            feedback="",
            memory_dir=args.memory_dir,
            model=args.model,
            iterations=args.training_iterations,
        )
        return

    task_cls = TASK_REGISTRY[args.task]
    for task in task_cls.from_cli_args(args):
        result = run_train_eval_loop(
            repo_path=args.repo,
            memory_dir=args.memory_dir,
            model=args.model,
            task=task,
            max_rounds=args.max_rounds,
            training_iterations=args.training_iterations,
        )
        logger.info(
            "task=%s passed=%s rounds_run=%d", args.task, result.passed, result.rounds_run
        )

if __name__ == "__main__":
    main()
