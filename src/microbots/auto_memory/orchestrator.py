"""Orchestrates the train <-> eval loop for repo-learning agents.

Repeatedly runs an ``EvalTask`` against a repo, and on failure builds
feedback and retrains via the training agent, looping until the task
passes or ``max_rounds`` is exhausted.
"""

from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.analyzer import build_feedback
from microbots.auto_memory.task import EvalOutcome, EvalTask
from microbots.auto_memory.training.runner import run_training

logger = getLogger(__name__)

@dataclass
class LoopResult:
    """Result of running ``run_train_eval_loop``.

    Attributes
    ----------
    passed : bool
        Whether the task passed within ``max_rounds``.
    rounds_run : int
        Number of eval rounds actually run.
    final_outcome : EvalOutcome
        The outcome of the last round run.
    outcomes : list[EvalOutcome]
        The outcome of every round run, in order.
    """

    passed: bool
    rounds_run: int
    final_outcome: EvalOutcome
    outcomes: list[EvalOutcome] = field(default_factory=list)

def run_train_eval_loop(
    repo_path: str,
    memory_dir: str,
    model: str,
    task: EvalTask,
    max_rounds: int = 5,
) -> LoopResult:
    """Run an eval task in a loop, retraining on failure until it passes.

    Each round runs ``task.run(...)``. If the task passes, the loop
    returns immediately. If it fails, feedback is built from the round's
    log and used to retrain via ``run_training`` before the next round.
    The round's log file is always deleted before the next round starts.

    Parameters
    ----------
    repo_path : str
        Absolute path to the repo to evaluate and train against.
    memory_dir : str
        Directory where the training agent reads/writes memory files.
    model : str
        The model to use, in the format ``<provider>/<model_name>``.
    task : EvalTask
        The eval task to run each round.
    max_rounds : int
        Maximum number of train/eval rounds to attempt. Defaults to 5.

    Returns
    -------
    LoopResult
        Whether the task passed, how many rounds ran, and every round's
        outcome.
    """
    outcomes: list[EvalOutcome] = []

    for round_idx in range(max_rounds):
        logger.info(
            "run_train_eval_loop: round %d/%d starting", round_idx + 1, max_rounds
        )
        outcome = task.run(repo_path, memory_dir, model)
        outcomes.append(outcome)

        try:
            if outcome.passed:
                logger.info(
                    "run_train_eval_loop: passed on round %d/%d", round_idx + 1, max_rounds
                )
                return LoopResult(
                    passed=True,
                    rounds_run=round_idx + 1,
                    final_outcome=outcome,
                    outcomes=outcomes,
                )

            logger.info(
                "run_train_eval_loop: round %d failed (%s), retraining",
                round_idx + 1,
                outcome.result.reason,
            )
            try:
                feedback = build_feedback(task, outcome, repo_path, model)

                run_training(
                    repo_path=repo_path,
                    feedback=feedback,
                    memory_dir=memory_dir,
                    model=model,
                )
            except Exception:
                logger.exception(
                    "run_train_eval_loop: round %d failed to build feedback/retrain; "
                    "continuing to next round without retraining",
                    round_idx + 1,
                )
        finally:
            Path(outcome.log_path).unlink(missing_ok=True)

    logger.info(
        "run_train_eval_loop: exhausted %d rounds without passing", max_rounds
    )
    return LoopResult(
        passed=False,
        rounds_run=max_rounds,
        final_outcome=outcomes[-1],
        outcomes=outcomes,
    )