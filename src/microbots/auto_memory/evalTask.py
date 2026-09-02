"""Defines the abstract eval task interface for the train <-> eval loop.

An ``EvalTask`` describes one unit of work: how to prepare a repo, what
prompt to give the agent, how to verify the agent's output, and how to
clean up afterward.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CallbackResult:
    """Result of verifying whether an eval task was completed correctly.

    Attributes
    ----------
    passed : bool
        Whether the agent's output satisfies the task's check.
    reason : str
        A short human-readable explanation of the pass/fail verdict.
    """

    passed: bool
    reason: str

@dataclass
class EvalOutcome:
    """Full record of one eval round.

    Attributes
    ----------
    passed : bool
        Whether the round passed, mirrors ``result.passed``.
    output : str | None
        The agent's raw output for the round, if any.
    result : CallbackResult
        The verdict produced by ``EvalTask.check``.
    """

    passed: bool
    output: str | None
    result: CallbackResult


class EvalTask(ABC):
    """Base class for a single evaluation task in the train <-> eval loop.

    Subclasses must implement ``run``. ``setup``, ``build_prompt``,
    ``check``, and ``teardown`` are optional hooks subclasses may use
    to structure their own ``run`` implementation (see
    ``SweBenchVerifiedTask`` for an example), but nothing in this base
    class calls them automatically.
    """

    @property
    def task_id(self) -> str:
        """Identifier for this task instance, used to name its output folder.

        Defaults to the class name, which is fine for tasks with only
        one instance per run. Override for tasks with several distinct
        instances per class (e.g. ``SweBenchVerifiedTask``, where each
        dataset row needs its own folder).

        Returns
        -------
        str
            This task instance's identifier.
        """
        return type(self).__name__

    def build_result(self, outcome: EvalOutcome) -> dict:
        """Optional. Build the dict written to this round's ``result.json``.

        Not called automatically; the orchestrator calls this after
        each round to decide what to persist. Override to include
        task-specific details (e.g. dataset fields, repo info).

        Parameters
        ----------
        outcome : EvalOutcome
            The round's outcome to summarize.

        Returns
        -------
        dict
            JSON-serializable summary. Defaults to ``passed``/``reason``.
        """
        return {"passed": outcome.result.passed, "reason": outcome.result.reason}

    def setup(self, repo_path: str) -> None:
        """Optional. Prepare repo/environment before the agent runs.

        Not called automatically; only useful if your ``run``
        implementation calls it.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo to prepare.
        """
        pass

    def build_prompt(self) -> str:
        """Optional. Return the task prompt/instructions for the agent.

        Not called automatically; only useful if your ``run``
        implementation calls it.

        Returns
        -------
        str
            The prompt/instructions to give the agent. Empty string by
            default.
        """
        return ""

    def check(self, repo_path: str, agent_output: str, log_path: str) -> CallbackResult:
        """Optional. Verify whether the task was actually completed correctly.

        Not called automatically; only useful if your ``run``
        implementation calls it.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo the agent operated on.
        agent_output : str
            The agent's raw output/result text.
        log_path : str
            Path to a log file, already created by ``run``, that this
            check may append verification details to.

        Returns
        -------
        CallbackResult
            The pass/fail verdict and its reason. Passes by default.
        """
        return CallbackResult(passed=True, reason="not checked")


    def teardown(self, repo_path: str) -> None:
        """Optional. Clean up anything setup() created.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo that was prepared by ``setup``.
        """
        pass

    @abstractmethod
    def build_feedback(self, outcome: EvalOutcome, repo_path: str, model: str, log_path: str) -> str:
        """Required. Analyze a failed eval outcome and produce training feedback.

        Called by the orchestrator after a failed round, before
        retraining, to turn the round's outcome/log into concrete
        feedback text describing what went wrong and what the agent's
        memory notes should cover next time.

        Parameters
        ----------
        outcome : EvalOutcome
            The failed outcome to analyze.
        repo_path : str
            Absolute path to the repo the task was evaluated against.
        model : str
            The model to use, in the format ``<provider>/<model_name>``.
        log_path : str
            Path to the round's log file, containing the agent output
            and any failure/exception details recorded during the
            round (the same path passed to ``run``).

        Returns
        -------
        str
            Feedback text to pass as ``feedback`` to the next round's
            training.
        """

    @abstractmethod
    def run(self, repo_path: str, memory_dir: str, model: str, log_path: str) -> EvalOutcome:
        """Required. Run one eval iteration and return its outcome.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo to run the eval round against.
        memory_dir : str
            Directory containing memory files to give the agent via
            ``MemoryTool``.
        model : str
            The model to use, in the format ``<provider>/<model_name>``.
        log_path : str
            Path to write this round's log to. Caller-provided (e.g. a
            workdir-managed path) so logs persist under the run's
            layout instead of each task inventing its own temp file.

        Returns
        -------
        EvalOutcome
            The result of this eval round, including the agent's output,
            the check verdict.
        """
