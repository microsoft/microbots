"""Build feedback text for a failed evaluation round.

Uses ``LogAnalysisBot`` to analyze the eval callback's raw log and produce
concrete feedback describing what went wrong, to be passed into the
training agent as ``feedback`` for the next round.
"""

from logging import getLogger

from microbots.auto_memory.task import EvalOutcome, EvalTask
from microbots.bot.LogAnalysisBot import LogAnalysisBot
from microbots.MicroBot import BotRunResult

logger = getLogger(__name__)
#make this abstract
def build_feedback(
    task: EvalTask,
    outcome: EvalOutcome,
    repo_path: str,
    model: str,
) -> str:
    """Analyze a failed eval outcome's log and produce training feedback.

    Parameters
    ----------
    task : EvalTask
        The eval task that produced ``outcome``.
    outcome : EvalOutcome
        The failed outcome to analyze, including its ``log_path``.
    repo_path : str
        Absolute path to the repo the task was evaluated against.
    model : str
        The model to use, in the format ``<provider>/<model_name>``.

    Returns
    -------
    str
        Feedback text describing the root cause of the failure and what
        the agent's memory notes should cover next time, suitable for
        passing as ``feedback`` to ``run_training``.
    """
    bot = LogAnalysisBot(model=model, folder_to_mount=repo_path)
    result: BotRunResult = bot.run(
        file_name=outcome.log_path,
        user_prompt=(
            "This log was produced while verifying whether an "
            "agent completed its task correctly. Identify "
            "the root cause of the failure and describe concretely "
            "what the agent's memory notes should cover next time to "
            "avoid this failure."
        ),
    )

    if result.status and result.result:
        return result.result

    logger.warning(
        "LogAnalysisBot failed to analyze failure (%s); falling back to plain feedback",
        result.error,
    )
    return (
        f"Evaluation failed. Agent output: {outcome.output}\n"
        f"Callback reason: {outcome.result.reason}"
    )
    