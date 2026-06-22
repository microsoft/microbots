"""Shared data models, enums, and value objects used across the auto_memory package."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


# Enums  (shared across orchestrator, callbacks, cli)

class IterationStatus(StrEnum):
    """Status of a single agent iteration."""
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


class FinalStatus(StrEnum):
    """Overall status of a completed auto_memory run."""
    PASSED = "passed"
    LIMIT_REACHED = "limit_reached"
    TIMEOUT = "timeout"
    ERROR = "error"


# Shared input value objects  (used by config.py)

@dataclass(frozen=True)
class ReferenceInput:
    """A named input to the task — either a literal value or a file path."""
    name: str
    value: str
    is_path: bool = False


@dataclass(frozen=True)
class CallbackSpec:
    """Specification for a single validator callback command.
    Shared between config.py (declaration) and callbacks.py (execution).
    """
    name: str
    command: str
    timeout_s: int = 120
    expected_return_code: int = 0


@dataclass
class Feedback:
    """Structured failure summary produced by analyze_failure().
    Written into MemoryStore so the agent reads it on the next iteration.
    """
    iteration_idx: int
    summary: str
    root_causes: list[str] = field(default_factory=list)
    validator_failures: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
