"""Base contracts for agent runners: IterationContext, AgentResult, AgentRunner."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from microbots.auto_memory.data_models import IterationStatus


@dataclass(frozen=True)
class IterationContext:
    """Immutable context for one agent invocation.

    Attributes
    ----------
    task : str
        The task prompt to send to the agent.
    memory_dir : str
        Host-side directory that is both mounted into the agent container
        (``folder_to_mount``) and surfaced to the agent via :class:`~microbots.tools.tool_definitions.memory_tool.MemoryTool`.
    output_dir : str
        Host-side directory (the iteration's ``candidate`` path) where the
        runner should write the artefact that callbacks validate. Callbacks
        receive this same path as ``$CANDIDATE``, so a runner that produces a
        file/tree here closes the produce → validate loop.
    """

    task: str
    memory_dir: str
    output_dir: str


@dataclass
class AgentResult:
    """Normalised result from a single agent run.

    Attributes
    ----------
    status : IterationStatus
        ``PASSED`` on success, ``TIMEOUT`` when the agent ran out of time,
        ``ERROR`` for all other failures.
    output : str | None
        The agent's final answer / thoughts when status is ``PASSED``.
    error : str | None
        Error description when status is not ``PASSED``.
    output_path : str | None
        Host-side path to the agent's output artefacts. Populated by the
        orchestrator after the agent run; runners leave this as ``None``.
    log_path : str | None
        Host-side path to the agent's execution log. Populated by the
        orchestrator after the agent run; runners leave this as ``None``.
    """

    status: IterationStatus
    output: str | None
    error: str | None
    output_path: str | None = None
    log_path: str | None = None


class AgentRunner(ABC):
    """Abstract base class for one auto-memory agent invocation."""

    @abstractmethod
    def run(self, ctx: IterationContext, timeout_s: int) -> AgentResult:
        """Run the agent described by *ctx* and return a normalised result.

        Parameters
        ----------
        ctx : IterationContext
            Task description and memory directory for this invocation.
        timeout_s : int
            Maximum wall-clock time the agent may use, in seconds.

        Returns
        -------
        AgentResult
            Normalised outcome of the agent run.
        """
