"""WritingBotRunner — the only module that imports microbots.bot.WritingBot.

This isolation keeps the core auto_memory framework decoupled from the
concrete bot implementation.
"""

from __future__ import annotations

from microbots.auto_memory.data_models import IterationStatus
from microbots.auto_memory.runners.base import AgentResult, AgentRunner, IterationContext
from microbots.bot.WritingBot import WritingBot
from microbots.MicroBot import BotRunResult
from microbots.tools.tool_definitions.memory_tool import MemoryTool

_TIMEOUT_ERROR_PREFIX = "Timeout of "


class WritingBotRunner:
    """Runs a :class:`~microbots.bot.WritingBot.WritingBot` for one iteration.

    Satisfies the :class:`AgentRunner` protocol structurally.

    Parameters
    ----------
    model : str
        Model identifier forwarded to ``WritingBot`` (e.g.
        ``"azure/gpt-4o"``).
    max_iterations : int, optional
        Maximum number of agent steps per run; forwarded to
        ``WritingBot.run()``. Defaults to 20.
    """

    def __init__(self, model: str, max_iterations: int = 20) -> None:
        """Store the model identifier and iteration cap used for every bot invocation.

        Parameters
        ----------
        model : str
            Model identifier forwarded to ``WritingBot`` (e.g. ``"azure/gpt-4o"``).
        max_iterations : int, optional
            Maximum number of agent steps per run. Defaults to 20.
        """
        self._model = model
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # AgentRunner implementation

    def run(self, ctx: IterationContext, timeout_s: int) -> AgentResult:
        """Create a fresh :class:`WritingBot`, run *ctx.task*, and return a
        normalised :class:`AgentResult`.

        The bot is configured with:

        * ``folder_to_mount=ctx.memory_dir`` so the container can read and
          write the iteration's memory directory.
        * ``MemoryTool(memory_dir=ctx.memory_dir)`` so the agent can call the
          ``memory`` tool to persist structured notes.

        Parameters
        ----------
        ctx : IterationContext
            Iteration context carrying the task and memory directory.
        timeout_s : int
            Per-iteration timeout forwarded to ``WritingBot.run()``.

        Returns
        -------
        AgentResult
            * ``PASSED`` when the bot completes the task successfully.
            * ``TIMEOUT`` when the bot's wall-clock limit is exceeded.
            * ``ERROR`` for all other failures (max-iterations reached, etc.).
        """
        bot = WritingBot(
            model=self._model,
            folder_to_mount=ctx.memory_dir,
            additional_tools=[MemoryTool(memory_dir=ctx.memory_dir)],
        )

        bot_result = bot.run(
            ctx.task,
            max_iterations=self._max_iterations,
            timeout_in_seconds=timeout_s,
        )

        return self._map_result(bot_result)

    # ------------------------------------------------------------------
    # Internal helpers

    @staticmethod
    def _map_result(bot_result: BotRunResult) -> AgentResult:
        """Convert a :class:`~microbots.MicroBot.BotRunResult` to an
        :class:`AgentResult`.

        Parameters
        ----------
        bot_result : BotRunResult
            Raw result returned by ``WritingBot.run()``.

        Returns
        -------
        AgentResult
            Normalised result with ``PASSED``, ``TIMEOUT``, or ``ERROR`` status.

        Notes
        -----
        Mapping rules:

        * ``status=True`` → ``PASSED``; ``output`` carries the bot's final answer.
        * ``status=False``, error contains ``"Timeout"`` → ``TIMEOUT``.
        * ``status=False``, all other errors → ``ERROR``.
        """
        if bot_result.status:
            return AgentResult(
                status=IterationStatus.PASSED,
                output=bot_result.result,
                error=None,
            )

        error_msg = bot_result.error or "Unknown error"

        if error_msg.startswith(_TIMEOUT_ERROR_PREFIX):
            return AgentResult(
                status=IterationStatus.TIMEOUT,
                output=None,
                error=error_msg,
            )

        return AgentResult(
            status=IterationStatus.ERROR,
            output=None,
            error=error_msg,
        )
