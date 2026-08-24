"""Command-line interface for the repository training agent."""

import argparse
import logging

from .runner import run_training

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
    return parser.parse_args()


def main():
    """Run repository training from command-line arguments."""
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    result = run_training(
        repo_path=args.repo,
        feedback=args.feedback,
        memory_dir=args.memory_dir,
        model=args.model,
    )
    logger.info("status=%s memory_dir=%s", result.status, args.memory_dir)
    if not result.status:
        logger.error("error=%s", result.error)


if __name__ == "__main__":
    main()

