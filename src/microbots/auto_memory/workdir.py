"""Path/layout helpers for a training run's workdir.

Centralizes every path this package reads or writes under a run's
``workdir`` (config, repo clone, logs, memory, and per-round/per-eval
outputs), so callers never hard-code layout details themselves.
"""

from pathlib import Path
import shutil

import yaml

WORKDIR_NAME = "workdir"
CONFIG_FILENAME = "config.yaml"
REPO_DIRNAME = "repo"
RUN_LOG_FILENAME = "run.log"
MEMORY_DIRNAME = "memory"
ROUNDS_DIRNAME = "rounds"
ROUND_LOG_FILENAME = "round.log"
ROUND_PATCH_FILENAME = "repo.patch"
EVAL_DIRNAME = "eval"
RESULT_FILENAME = "result.json"
EVAL_LOG_FILENAME = "eval.log"


def resolve_workdir(base: Path | None = None) -> Path:
    """Resolve the fixed workdir path relative to ``base``.

    Parameters
    ----------
    base : Path | None
        Directory to resolve ``workdir/`` relative to. Defaults to the
        current working directory.

    Returns
    -------
    Path
        ``workdir`` resolved relative to ``base`` (or ``Path.cwd()``).
    """
    return (base or Path.cwd()) / WORKDIR_NAME


def require_workdir(workdir: Path) -> None:
    """Validate that ``workdir`` exist.

    Parameters
    ----------
    workdir : Path
        The workdir to validate.

    Raises
    ------
    FileNotFoundError
        If ``workdir`` does not exist.
    """
    if not workdir.is_dir():
        raise FileNotFoundError(f"workdir not found: {workdir}")


def config_path(workdir: Path) -> Path:
    """Return the path to ``workdir``'s config file.

    Parameters
    ----------
    workdir : Path
        The run's workdir.

    Returns
    -------
    Path
        ``workdir/config.yaml``.
    """
    return workdir / CONFIG_FILENAME


def load_config(workdir: Path) -> dict:
    """Load and parse ``workdir``'s config file.

    Parameters
    ----------
    workdir : Path
        The workdir whose config file should be loaded.

    Returns
    -------
    dict
        The parsed config, or ``{}`` if the config file doesn't exist
        or is empty.
    """
    path = config_path(workdir)
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def repo_dir(workdir: Path) -> Path:
    """Return the path to the single cloned repo shared across rounds.

    Parameters
    ----------
    workdir : Path
        The run's workdir.

    Returns
    -------
    Path
        ``workdir/repo``.
    """
    return workdir / REPO_DIRNAME


def run_log_path(workdir: Path) -> Path:
    """Return the path to the top-level orchestrator log.

    Parameters
    ----------
    workdir : Path
        The run's workdir.

    Returns
    -------
    Path
        ``workdir/run.log``.
    """
    return workdir / RUN_LOG_FILENAME


def memory_dir(workdir: Path) -> Path:
    """Return the path to the current top-level (latest) memory directory.

    Parameters
    ----------
    workdir : Path
        The run's workdir.

    Returns
    -------
    Path
        ``workdir/memory``.
    """
    return workdir / MEMORY_DIRNAME


def round_dir(
    workdir: Path, round_num: int, *, instance_id: str | None = None, create: bool = False
) -> Path:
    """Return (and optionally create) the directory for a training round.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number.
    instance_id : str | None
        If given, rounds are kept under a per-instance rounds dir
        (``rounds_{instance_id}``) instead of the shared ``rounds`` dir,
        so different eval task instances sharing the same ``workdir``
        don't collide on round numbers. Pass the eval task's
        ``task_id`` when running an eval task; omit for training-only
        mode.
    create : bool
        If True, create the directory (and parents) if missing.

    Returns
    -------
    Path
        ``workdir/rounds/round_{round_num}`` (no ``instance_id``), or
        ``workdir/rounds_{instance_id}/round_{round_num}``.
    """
    rounds_dirname = f"{ROUNDS_DIRNAME}_{instance_id}" if instance_id else ROUNDS_DIRNAME
    path = workdir / rounds_dirname / f"round_{round_num}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def round_memory_dir(workdir: Path, round_num: int, *, instance_id: str | None = None) -> Path:
    """Return the path to a round's own memory snapshot (a directory).

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number.
    instance_id : str | None
        The eval task's ``task_id``, if running an eval task (see
        ``round_dir``). Omit for training-only mode.

    Returns
    -------
    Path
        This round's own memory directory.
    """
    return round_dir(workdir, round_num, instance_id=instance_id) / MEMORY_DIRNAME


def load_round_memory(workdir: Path, round_num: int, *, instance_id: str | None = None) -> Path:
    """Copy the current top-level memory into this round's own memory dir.

    Called before a round's training pass, so it starts from whatever
    memory the previous round left behind (or empty, on round 1).

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number to load memory into.
    instance_id : str | None
        The eval task's ``task_id``, if running an eval task (see
        ``round_dir``). Omit for training-only mode.

    Returns
    -------
    Path
        This round's own memory dir, ready for the round to use.
    """
    src = memory_dir(workdir)
    dst = round_memory_dir(workdir, round_num, instance_id=instance_id)
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def save_round_memory(workdir: Path, round_num: int, *, instance_id: str | None = None) -> Path:
    """Copy this round's memory back up to the top-level memory dir.

    Called after a round's training pass, so later rounds (and the
    final saved memory) see what this round learned.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number whose memory should be saved.
    instance_id : str | None
        The eval task's ``task_id``, if running an eval task (see
        ``round_dir``). Omit for training-only mode.

    Returns
    -------
    Path
        The top-level ``memory`` dir, now updated with this round's changes.
    """
    src = round_memory_dir(workdir, round_num, instance_id=instance_id)
    dst = memory_dir(workdir)
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def round_log_path(workdir: Path, round_num: int, *, instance_id: str | None = None) -> Path:
    """Return the path to a round's training log.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number.
    instance_id : str | None
        The eval task's ``task_id``, if running an eval task (see
        ``round_dir``). Omit for training-only mode.

    Returns
    -------
    Path
        This round's ``round.log``.
    """
    return round_dir(workdir, round_num, instance_id=instance_id) / ROUND_LOG_FILENAME


def eval_dir(
    workdir: Path, round_num: int, instance_id: str, *, create: bool = False
) -> Path:
    """Return (and optionally create) an eval task instance's eval directory.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number this eval instance belongs to.
    instance_id : str
        The eval task instance identifier.
    create : bool
        If True, create the directory (and parents) if missing.

    Returns
    -------
    Path
        ``workdir/rounds_{instance_id}/round_{round_num}/eval``.
    """
    path = round_dir(workdir, round_num, instance_id=instance_id) / EVAL_DIRNAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def eval_result_path(workdir: Path, round_num: int, instance_id: str) -> Path:
    """Return the path to an eval instance's result file.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number this eval instance belongs to.
    instance_id : str
        The eval task instance identifier.

    Returns
    -------
    Path
        This eval instance's ``result.json``.
    """
    return eval_dir(workdir, round_num, instance_id) / RESULT_FILENAME


def eval_log_path(workdir: Path, round_num: int, instance_id: str) -> Path:
    """Return the path to an eval instance's log file.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number this eval instance belongs to.
    instance_id : str
        The eval task instance identifier.

    Returns
    -------
    Path
        This eval instance's ``eval.log``.
    """
    return eval_dir(workdir, round_num, instance_id) / EVAL_LOG_FILENAME


def eval_patch_path(workdir: Path, round_num: int, instance_id: str) -> Path:
    """Return the path to an eval instance's captured repo diff.

    Parameters
    ----------
    workdir : Path
        The run's workdir.
    round_num : int
        1-based round number this eval instance belongs to.
    instance_id : str
        The eval task instance identifier.

    Returns
    -------
    Path
        This eval instance's ``repo.patch``.
    """
    return eval_dir(workdir, round_num, instance_id) / ROUND_PATCH_FILENAME