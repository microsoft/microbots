"""Agent runner abstractions for the auto_memory package.

The only concrete runner that imports WritingBot lives in
``writing_bot_runner`` so the core framework stays decoupled from the
concrete bot implementation.

Exported names:

* ``IterationContext`` — immutable context passed to every :class:`AgentRunner`.
* ``AgentResult`` — normalised result returned by every runner.
* ``AgentRunner`` — structural protocol satisfied by any runner with a matching
  ``run`` method.
"""

from microbots.auto_memory.runners.base import AgentResult, AgentRunner, IterationContext

__all__ = ["IterationContext", "AgentResult", "AgentRunner"]
