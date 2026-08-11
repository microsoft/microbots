"""Agent runner for training iterations.

Wraps :class:`~microbots.bot.ReadingBot.ReadingBot` so that:

* the source directory the agent should learn from is mounted into the
  sandbox as the working directory (``folder_to_mount``); and
* the agent's ``/memories/`` tree is backed by a host-side directory that
  survives across iterations and runs.

The framework does not assume the source is a source-code repository — it
can be any directory. This is the *only* module in
:mod:`microbots.auto_memory.training` that imports the concrete bot
implementation, keeping the training loop itself decoupled.
"""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.data_models import IterationStatus
from microbots.bot.ReadingBot import ReadingBot
from microbots.MicroBot import BotRunResult
from microbots.tools.tool_definitions.memory_tool import MemoryTool

logger = getLogger(__name__)

_TIMEOUT_PREFIX = "Timeout of "


@dataclass(frozen=True)
class TrainingIterationResult:
    """Normalised outcome of one training iteration.

    Attributes
    ----------
    status : IterationStatus
        One of ``PASSED``, ``TIMEOUT``, ``ERROR``.
    output : str | None
        Bot's final answer on success, else ``None``.
    error : str | None
        Error description on failure, else ``None``.
    """

    status: IterationStatus
    output: str | None
    error: str | None


class LearningRunner:
    """Runs one :class:`ReadingBot` iteration against a mounted source directory.

    Parameters
    ----------
    model : str
        Model identifier forwarded to :class:`ReadingBot`.
    source_path : Path
        Directory mounted into the sandbox as the material the agent should
        learn from. May be a source-code repo, a docs tree, a dataset, or
        any other directory.
    memory_dir : Path
        Host-side directory backing the agent's ``/memories/`` tree.
    max_bot_steps : int, optional
        ``max_iterations`` forwarded to :meth:`ReadingBot.run`. Defaults to
        ``40``.
    """

    def __init__(
        self,
        *,
        model: str,
        source_path: Path,
        memory_dir: Path,
        max_bot_steps: int = 40,
    ) -> None:
        """Initialize a runner for one training source.

        Parameters
        ----------
        model : str
            Model identifier forwarded to the bot.
        source_path : Path
            Directory mounted as the bot's working directory.
        memory_dir : Path
            Host directory backing the bot's persistent memory.
        max_bot_steps : int, optional
            Maximum internal bot steps per invocation.
        """
        self._model = model
        self._source_path = source_path
        self._memory_dir = memory_dir
        self._max_bot_steps = max_bot_steps

    # ------------------------------------------------------------------

    def run(self, task_prompt: str, timeout_s: int) -> TrainingIterationResult:
        """Execute one bot invocation and return a normalised result.

        Parameters
        ----------
        task_prompt : str
            Full prompt (typically the AGENTS.md contents plus an iteration
            header) passed to the bot as its task.
        timeout_s : int
            Per-iteration wall-clock cap forwarded to :meth:`ReadingBot.run`.

        Returns
        -------
        TrainingIterationResult
            Normalised outcome. Never raises for a failed iteration; only
            configuration or infrastructure errors propagate.
        """
        bot = ReadingBot(
            model=self._model,
            folder_to_mount=str(self._source_path),
            additional_tools=[MemoryTool(memory_dir=str(self._memory_dir))],
        )

        bot_result: BotRunResult = bot.run(
            task_prompt,
            max_iterations=self._max_bot_steps,
            timeout_in_seconds=timeout_s,
        )

        return self._map(bot_result)

    # ------------------------------------------------------------------

    @staticmethod
    def _map(bot_result: BotRunResult) -> TrainingIterationResult:
        """Map a bot result to the training iteration result model.

        Parameters
        ----------
        bot_result : BotRunResult
            Raw result returned by the bot.

        Returns
        -------
        TrainingIterationResult
            Normalized passed, timeout, or error result.
        """
        if bot_result.status:
            return TrainingIterationResult(
                status=IterationStatus.PASSED, output=bot_result.result, error=None
            )

        error = bot_result.error or "Unknown error"
        if error.startswith(_TIMEOUT_PREFIX):
            return TrainingIterationResult(
                status=IterationStatus.TIMEOUT, output=None, error=error
            )
        return TrainingIterationResult(
            status=IterationStatus.ERROR, output=None, error=error
        )
