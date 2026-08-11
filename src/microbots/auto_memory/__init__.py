"""Iterative agent loop with memory feedback (auto_memory package)."""

from microbots.auto_memory.callbacks import CallbackResult, CallbackRunner
from microbots.auto_memory.cli import run_from_yaml
from microbots.auto_memory.config import DEFAULT_PROMPT_TEMPLATE, TaskConfig
from microbots.auto_memory.data_models import (
    CallbackSpec,
    Feedback,
    FinalStatus,
    IterationStatus,
    ReferenceInput,
)
from microbots.auto_memory.errors import (
    AgentError,
    AutoMemoryError,
    AutoMemoryTimeoutError,
    CallbackError,
    ConfigError,
    MemoryStoreError,
)
from microbots.auto_memory.memory import MemoryStore
from microbots.auto_memory.orchestrator import (
    IterationRecord,
    RunSummary,
    TrainingLoopOrchestrator,
)
from microbots.auto_memory.runners import AgentResult, AgentRunner, IterationContext
from microbots.auto_memory.runners.writing_bot_runner import WritingBotRunner
from microbots.auto_memory.workspace import WorkspaceManager

__all__ = [
    "CallbackResult",
    "CallbackRunner",
    "CallbackSpec",
    "DEFAULT_PROMPT_TEMPLATE",
    "AgentResult",
    "AgentRunner",
    "IterationContext",
    "IterationRecord",
    "IterationStatus",
    "FinalStatus",
    "Feedback",
    "ReferenceInput",
    "RunSummary",
    "MemoryStore",
    "WorkspaceManager",
    "TrainingLoopOrchestrator",
    "TaskConfig",
    "WritingBotRunner",
    "run_from_yaml",
    "AutoMemoryError",
    "ConfigError",
    "AgentError",
    "CallbackError",
    "AutoMemoryTimeoutError",
    "MemoryStoreError",
]