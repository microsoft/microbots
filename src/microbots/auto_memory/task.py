"""Defines the abstract eval task interface for the train <-> eval loop.

An ``EvalTask`` describes one unit of work: how to prepare a repo, what
prompt to give the agent, how to verify the agent's output, and how to
clean up afterward.
"""

import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

from microbots.bot.WritingBot import WritingBot
from microbots.tools.tool_definitions.memory_tool import MemoryTool

logger = getLogger(__name__)

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

    Subclasses must implement ``setup``, ``build_prompt``, and ``check``,
    and may override ``teardown`` and ``run`` as needed.
    """

    @abstractmethod
    def setup(self, repo_path: str) -> None:
        """Required. Prepare repo/environment before the agent runs.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo to prepare.
        """

    @abstractmethod
    def build_prompt(self, repo_path: str) -> str:
        """Required. Return the task prompt/instructions for the agent.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo the agent will operate on.

        Returns
        -------
        str
            The prompt/instructions to give the agent.
        """

    @abstractmethod
    def check(self, repo_path: str, agent_output: str, log_path: str) -> CallbackResult:
        """Required. Verify whether the task was actually completed correctly.

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
            The pass/fail verdict and its reason.
        """

    def teardown(self, repo_path: str) -> None:
        """Optional. Clean up anything setup() created.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo that was prepared by ``setup``.
        """
        pass

    def run(self, repo_path: str, memory_dir: str, model: str) -> EvalOutcome:
        """Default eval iteration: setup -> build_prompt -> WritingBot -> check -> teardown.
        Override this entirely if your task needs a different bot type,
        additional tools, or custom retry/orchestration logic.

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
        self.setup(repo_path)
        log_path = tempfile.mktemp(suffix=".log")
        Path(log_path).write_text("")

        try:
            try:
                prompt = self.build_prompt(repo_path)
                bot = WritingBot(
                    model=model,
                    folder_to_mount=repo_path,
                    additional_tools=[MemoryTool(memory_dir=memory_dir)],
                )
                bot_result = bot.run(prompt)

                with open(log_path, "a") as f:
                    f.write(f"Agent output:\n{bot_result.result}\n")

                if not bot_result.status:
                    reason = f"Bot run failed: {bot_result.error}"
                    with open(log_path, "a") as f:
                        f.write(f"\n{reason}\n")
                    result = CallbackResult(passed=False, reason=reason)
                else:
                    result = self.check(repo_path, bot_result.result or "", log_path)

                return EvalOutcome(
                    passed=result.passed,
                    output=bot_result.result,
                    result=result,
                    log_path=log_path,
                )
            except Exception as exc:
                logger.exception(
                    "EvalTask.run: iteration raised %s", type(exc).__name__
                )
                with open(log_path, "a") as f:
                    f.write(f"\nException during eval iteration: {type(exc).__name__}: {exc}\n")
                return EvalOutcome(
                    passed=False,
                    output=None,
                    result=CallbackResult(
                        passed=False, reason=f"{type(exc).__name__}: {exc}"
                    ),
                    log_path=log_path,
                )
        finally:
            try:
                self.teardown(repo_path)
            except Exception:
                logger.exception("EvalTask.run: teardown() raised exception; ignoring")
