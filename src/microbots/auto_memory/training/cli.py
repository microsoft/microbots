"""Command-line interface for the repository training agent."""

import argparse
import logging

from .runner import run_training_loop

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments for a training run.

    Returns
    -------
    argparse.Namespace
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Training agent")
    parser.add_argument("--repo", required=True, help="Path or URL to the repo to learn from")
    parser.add_argument("--feedback", default="", help="Optional feedback text (can be empty)")
    parser.add_argument("--memory-dir", default="./memory", help="Directory to store the memory file")
    parser.add_argument("--model", required=True, help="Model identifier, e.g. azure-openai/gpt-4o")
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of training passes to run in sequence over the same memory_dir",
    )
    return parser.parse_args()


def main():
    """Run repository training from command-line arguments."""
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    result = run_training_loop(
        repo_path=args.repo,
        feedback=args.feedback,
        memory_dir=args.memory_dir,
        model=args.model,
        iterations=args.iterations,
    )
    if not result.status:
        logger.error("training loop finished with failure: %s", result.error)


if __name__ == "__main__":
    main()

