"""On-disk workspace layout manager for auto_memory runs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.memory import MemoryStore

logger = getLogger(__name__)

_META_FILE = "run_meta.json"
_ITER_PREFIX = "iter_"


@dataclass
class WorkspaceManager:
    """Creates and manages the on-disk layout for a single auto_memory run.

    On-disk layout::

        <run_dir>/
        ├── memory/
        │   └── feedback.jsonl          ← managed by MemoryStore
        ├── iterations/
        │   ├── iter_00/
        │   │   ├── candidate/          ← agent writes output here
        │   │   └── logs/               ← callback stdout / stderr
        │   └── iter_01/
        │       └── ...
        └── run_meta.json               ← created_at, run_dir

    Typical usage::

        wm = WorkspaceManager(run_dir=Path("runs/my_task"))
        wm.prepare()                            # or prepare(resume=True)

        idir = wm.prepare_iteration(0)          # creates iter_00/
        # ... agent writes to idir / "candidate" ...
        wm.memory.append_feedback(feedback)

        wm.cleanup()                            # strip __pycache__ etc.
    """

    run_dir: Path
    memory: MemoryStore = field(default_factory=MemoryStore)

    # Set by prepare(); not part of the constructor signature.
    _iterations_dir: Path = field(init=False, repr=False)
    _iteration_count: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        """Initialise derived path attributes after dataclass construction."""
        self._iterations_dir = self.run_dir / "iterations"

    # ------------------------------------------------------------------
    # Lifecycle

    def prepare(self, *, resume: bool = False) -> None:
        """Create (or resume) the run directory layout.

        ``resume=False`` (default): if *run_dir* already exists it is
        **wiped** before creating a fresh layout.  ``resume=True``: *run_dir*
        must already exist; its contents are preserved and the number of
        already-completed iterations is detected from the filesystem.

        The owned :attr:`memory` store is mounted with the same *resume* flag.

        Parameters
        ----------
        resume : bool, optional
            When ``True``, continue a previously started run.

        Raises
        ------
        ConfigError
            If ``resume=True`` but *run_dir* does not exist.
        """
        exists = self.run_dir.exists()

        if resume and not exists:
            raise ConfigError(
                f"resume=True but run directory does not exist: {self.run_dir}"
            )

        if not resume and exists:
            self._safe_rmtree(self.run_dir)
            logger.debug(
                "WorkspaceManager: wiping existing run_dir %s", self.run_dir
            )

        # (Re-)create top-level directories.
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._iterations_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            self._iteration_count = self._detect_iteration_count()
            logger.debug(
                "WorkspaceManager: resuming — found %d prior iteration(s)",
                self._iteration_count,
            )
        else:
            self._iteration_count = 0
            self._write_meta()

        self.memory.mount(self.run_dir, resume=resume)

    def reset(self) -> None:
        """Wipe *run_dir* and create a fresh layout.

        Equivalent to calling ``prepare(resume=False)`` after the workspace
        has already been prepared.
        """
        self.prepare(resume=False)

    def cleanup(self) -> None:
        """Remove ephemeral artifacts from the run directory.

        Deletes all ``__pycache__`` directories and ``*.pyc`` files found
        anywhere under *run_dir*.  Result files and memory are preserved.
        """
        for pycache in self.run_dir.rglob("__pycache__"):
            shutil.rmtree(pycache, ignore_errors=True)
        for pyc in self.run_dir.rglob("*.pyc"):
            pyc.unlink(missing_ok=True)
        logger.debug("WorkspaceManager: cleanup complete for %s", self.run_dir)

    # ------------------------------------------------------------------
    # Iteration helpers

    @property
    def iteration_count(self) -> int:
        """Number of iterations prepared so far.

        Returns
        -------
        int
            Count of iterations prepared via :meth:`prepare_iteration`.
        """
        return self._iteration_count

    def iteration_dir(self, idx: int) -> Path:
        """Return the path for iteration *idx* (zero-based).

        The directory is **not** created by this call; use
        :meth:`prepare_iteration` to create it.

        Parameters
        ----------
        idx : int
            Zero-based iteration index.

        Returns
        -------
        Path
            Path to the ``iter_<idx>`` directory.
        """
        return self._iterations_dir / f"{_ITER_PREFIX}{idx:02d}"

    def prepare_iteration(self, idx: int) -> Path:
        """Create the subdirectory tree for iteration *idx* and return it.

        Creates::

            iterations/iter_<idx>/
            ├── candidate/
            └── logs/

        Parameters
        ----------
        idx : int
            Zero-based iteration index.

        Returns
        -------
        Path
            The ``iter_<idx>`` directory path.

        Raises
        ------
        ConfigError
            If *idx* is negative.
        """
        if idx < 0:
            raise ConfigError(
                f"Iteration index must be >= 0, got {idx}"
            )
        idir = self.iteration_dir(idx)
        (idir / "candidate").mkdir(parents=True, exist_ok=True)
        (idir / "logs").mkdir(parents=True, exist_ok=True)
        self._iteration_count = max(self._iteration_count, idx + 1)
        logger.debug("WorkspaceManager: prepared iteration dir %s", idir)
        return idir

    # ------------------------------------------------------------------
    # Internals

    @staticmethod
    def _safe_rmtree(path: Path) -> None:
        """Remove *path* recursively after guarding against dangerous targets.

        Refuses to delete the filesystem root or any path with fewer than
        two resolved components (e.g. ``/tmp``, ``/home``).

        Parameters
        ----------
        path : Path
            Directory to remove.

        Raises
        ------
        ConfigError
            If *path* resolves to a root or near-root directory.
        """
        resolved = path.resolve()
        # Guard: must have at least 2 parent levels (e.g. /a/b/c is fine; /a is not).
        if len(resolved.parts) <= 2:  # ('/', 'a') → parts length 2
            raise ConfigError(
                f"Refusing to delete a root or near-root path: {resolved}"
            )
        shutil.rmtree(path)

    def _detect_iteration_count(self) -> int:
        """Return highest existing iteration index + 1 (or 0 if none).

        Returns
        -------
        int
            Number of iterations detected from the filesystem.
        """
        if not self._iterations_dir.exists():
            return 0

        max_idx = -1
        for p in self._iterations_dir.iterdir():
            if not (p.is_dir() and p.name.startswith(_ITER_PREFIX)):
                continue
            suffix = p.name[len(_ITER_PREFIX):]
            if suffix.isdigit():
                max_idx = max(max_idx, int(suffix))

        return max_idx + 1 if max_idx >= 0 else 0

    def _write_meta(self) -> None:
        """Write run metadata (creation timestamp, run_dir) to ``run_meta.json``."""
        meta = {
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "run_dir": str(self.run_dir),
        }
        try:
            (self.run_dir / _META_FILE).write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not write %s: %s", _META_FILE, exc)
