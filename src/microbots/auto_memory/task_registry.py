"""Registry for constructing ``EvalTask`` instances by name.

Tasks self-register via the ``@register_task`` decorator, so new task
types can be added without editing a central if/elif factory function.
Callers (e.g. a CLI) look tasks up by name via ``create_task``.
"""

import importlib
import pkgutil

from microbots.auto_memory.task import EvalTask

TASK_REGISTRY: dict[str, type[EvalTask]] = {}

def register_task(name: str):
    """Register an ``EvalTask`` subclass under ``name`` as a class decorator.

    Parameters
    ----------
    name : str
        The key other code will use to look up this task via
        ``create_task``, e.g. ``"swebenchverified"``.

    Returns
    -------
    Callable[[type[EvalTask]], type[EvalTask]]
        A decorator that registers the class in ``TASK_REGISTRY`` and
        returns it unchanged.
    """

    def decorator(task_cls: type[EvalTask]) -> type[EvalTask]:
        """Register ``task_cls`` in ``TASK_REGISTRY`` under the enclosing ``name``.

        Parameters
        ----------
        task_cls : type[EvalTask]
            The ``EvalTask`` subclass to register.

        Returns
        -------
        type[EvalTask]
            ``task_cls``, unchanged.
        """
        TASK_REGISTRY[name] = task_cls
        return task_cls

    return decorator

def create_task(name: str, **kwargs) -> EvalTask:
    """Construct a registered ``EvalTask`` by name.

    Parameters
    ----------
    name : str
        The registered task name, e.g. ``"swebenchverified"``.
    **kwargs
        Keyword arguments forwarded to the task's constructor.

    Returns
    -------
    EvalTask
        The constructed task instance.

    Raises
    ------
    ValueError
        If ``name`` has not been registered via ``register_task``.
    """
    try:
        task_cls = TASK_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown task {name!r}. Registered tasks: {sorted(TASK_REGISTRY)}"
        ) from None
    return task_cls(**kwargs)

def discover_tasks(package_name: str = "microbots.auto_memory.eval") -> None:
    """Import every module in ``package_name`` so ``@register_task`` fires.

    Adding a new task only requires dropping a new module into this
    package (with its own ``@register_task`` decorator) — no other code
    needs to change to make it discoverable.

    Parameters
    ----------
    package_name : str
        Dotted path of the package to scan for task modules. Defaults
        to ``"microbots.auto_memory.eval"``.
    """
    package = importlib.import_module(package_name)
    for module_info in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package_name}.{module_info.name}")
