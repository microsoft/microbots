"""Utilities for building iteration context prompts from task configuration."""

from __future__ import annotations

from jinja2 import Environment as JinjaEnvironment, StrictUndefined

from microbots.auto_memory.config import TaskConfig
from microbots.auto_memory.data_models import Feedback

_JINJA_ENV = JinjaEnvironment(undefined=StrictUndefined, keep_trailing_newline=True)


def build_iteration_context(
    config: TaskConfig,
    iteration_idx: int,
    *,
    feedback: Feedback | None = None,
) -> str:
    """Render the prompt template for one iteration.

    The following variables are available inside the Jinja2 template:

    * ``task`` — the ``task_definition`` string from *config*.
    * ``iteration_idx`` — zero-based iteration number.
    * ``reference_inputs`` — ``list[ReferenceInput]`` from *config*; each
      item exposes ``.name``, ``.value``, and ``.is_path``.
    * ``feedback`` — the :class:`~microbots.auto_memory.data_models.Feedback`
      from the previous iteration, or ``None`` on the first iteration.

    Parameters
    ----------
    config : TaskConfig
        The task configuration whose ``prompt_template`` is rendered.
    iteration_idx : int
        Zero-based index of the current iteration.
    feedback : Feedback | None, optional
        Structured feedback from the previous iteration, or ``None`` if
        this is the first iteration.

    Returns
    -------
    str
        The rendered prompt text, ready to be sent to the agent.
    """
    env = _JINJA_ENV
    template = env.from_string(config.prompt_template)
    return template.render(
        task=config.task_definition,
        iteration_idx=iteration_idx,
        reference_inputs=config.reference_inputs,
        feedback=feedback,
    )
