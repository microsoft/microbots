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
    log_path : str
        Path to the round's log file, containing the agent output and
        any failure/exception details recorded during the round.
    """

    passed: bool
    output: str | None
    result: CallbackResult
    log_path: str


class EvalTask(ABC):
    """Base class for a single evaluation task in the train <-> eval loop.

    Subclasses must implement ``run``. ``setup``, ``build_prompt``,
    ``check``, and ``teardown`` are optional hooks subclasses may use
    to structure their own ``run`` implementation (see
    ``SweBenchVerifiedTask`` for an example), but nothing in this base
    class calls them automatically.
    """

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

    def build_prompt(self, repo_path: str) -> str:
        """Optional. Return the task prompt/instructions for the agent.

        Not called automatically; only useful if your ``run``
        implementation calls it.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo the agent will operate on.

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
    def run(self, repo_path: str, memory_dir: str, model: str) -> EvalOutcome:
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

        Returns
        -------
        EvalOutcome
            The result of this eval round, including the agent's output,
            the check verdict, and the round's log file path.
        """
