class AutoMemoryError(Exception):
    """Base class for all auto_memory framework errors."""


class ConfigError(AutoMemoryError):
    """Raised when TaskConfig is invalid or cannot be loaded."""


class AgentError(AutoMemoryError):
    """Raised when the agent runner encounters an unrecoverable error."""


class CallbackError(AutoMemoryError):
    """Raised when a callback cannot be spawned or set up (not a failing assertion)."""


class TimeoutError(AutoMemoryError):  # noqa: A001 — intentional shadow of builtin
    """Raised when the per-iteration or total run timeout is exceeded."""


class MemoryStoreError(AutoMemoryError):
    """Raised when the memory store cannot be read from or written to."""
