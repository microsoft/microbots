"""Training subpackage for auto_memory.

Houses the learning phase that is fully independent of the eval loop in
:mod:`microbots.auto_memory`. The only shared surface between the two
phases is (eventually) :class:`~microbots.auto_memory.repo_memory.RepoMemory`.

The framework is domain-agnostic: an ``AGENTS.md`` file defines *what* the
agent should learn, a source directory is mounted into the sandbox as the
material to learn *from*, and a ``memory_dir`` collects the resulting
notes. The default ``AGENTS.md`` shipped in this package targets
repository learning, but the framework itself makes no such assumption \u2014
the source can be a source-code repo, a docs tree, a dataset, an example
gallery, or anything else that fits in a directory.

Public API
  (an existing local path or a git repo to clone).
  notes in a shared ``/memories/`` tree.
  points.
"""

from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.training_source import TrainingSource
from microbots.auto_memory.training.orchestrator import (
    TrainingFinalStatus,
    TrainingIterationRecord,
    TrainingOrchestrator,
    TrainingSummary,
)
from microbots.auto_memory.training.cli import (
    run_training,
    run_training_from_yaml,
)

__all__ = [
    "TrainingConfig",
    "TrainingSource",
    "TrainingOrchestrator",
    "TrainingSummary",
    "TrainingIterationRecord",
    "TrainingFinalStatus",
    "run_training",
    "run_training_from_yaml",
]

