"""JSONL-backed persistent memory store for auto_memory feedback."""

from __future__ import annotations

import dataclasses
import json
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.data_models import Feedback
from microbots.auto_memory.errors import MemoryStoreError

logger = getLogger(__name__)

_FEEDBACK_FILE = "feedback.jsonl"


class MemoryStore:
    """Persistent memory store backed by a JSONL file.

    Each :class:`~microbots.auto_memory.data_models.Feedback` entry is
    serialised as a single JSON line in ``<run_dir>/memory/feedback.jsonl``.
    Calls to :meth:`append_feedback` write immediately (no buffering);
    :meth:`persist` is a no-op provided for interface symmetry.

    Usage::

        store = MemoryStore()
        store.mount(run_dir)                         # or resume=True
        store.append_feedback(feedback)
        entries = store.read_all()
        store.clear()
    """

    def __init__(self) -> None:
        """Initialise an unmounted store; call :meth:`mount` before use."""
        self._memory_dir: Path | None = None
        self._feedback_path: Path | None = None

    # ------------------------------------------------------------------
    # Lifecycle

    def mount(self, run_dir: Path, *, resume: bool = False) -> None:
        """Attach the store to *run_dir/memory/*.

        ``resume=False`` (default): the feedback file is wiped so the new
        run starts with a clean slate.  ``resume=True``: if the file already
        exists its contents are kept so the run can continue from the
        previous state.

        Parameters
        ----------
        run_dir : Path
            Root directory of the auto_memory run.
        resume : bool, optional
            When ``True``, preserve any existing feedback file.

        Raises
        ------
        MemoryStoreError
            If the memory directory cannot be created.
        """
        memory_dir = run_dir / "memory"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MemoryStoreError(
                f"Cannot create memory directory {memory_dir}: {exc}"
            ) from exc

        self._memory_dir = memory_dir
        self._feedback_path = memory_dir / _FEEDBACK_FILE

        if not resume:
            self.clear()

        logger.debug(
            "MemoryStore mounted at %s (resume=%s)", memory_dir, resume
        )

    # ------------------------------------------------------------------
    # Read / write

    def append_feedback(self, feedback: Feedback) -> None:
        """Append one *feedback* entry to the JSONL file.

        Parameters
        ----------
        feedback : Feedback
            The feedback object to serialise and append.

        Raises
        ------
        MemoryStoreError
            If not mounted or on I/O error.
        """
        self._require_mounted()
        try:
            with self._feedback_path.open("a", encoding="utf-8") as fh:  # type: ignore[union-attr]
                fh.write(json.dumps(dataclasses.asdict(feedback)) + "\n")
        except OSError as exc:
            raise MemoryStoreError(f"Failed to write feedback: {exc}") from exc

    def read_all(self) -> list[Feedback]:
        """Return all persisted :class:`~microbots.auto_memory.data_models.Feedback` entries.

        Returns an empty list if the feedback file does not exist yet.

        Returns
        -------
        list[Feedback]
            All feedback entries in the order they were appended.

        Raises
        ------
        MemoryStoreError
            If not mounted or on I/O / parse error.
        """
        self._require_mounted()
        if not self._feedback_path.exists():  # type: ignore[union-attr]
            return []

        entries: list[Feedback] = []
        try:
            with self._feedback_path.open("r", encoding="utf-8") as fh:  # type: ignore[union-attr]
                for lineno, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Skipping corrupt JSON on line %d of %s: %s",
                            lineno,
                            self._feedback_path,
                            exc,
                        )
                        continue
                    if not isinstance(data, dict):
                        logger.warning(
                            "Skipping non-object entry on line %d of %s (got %s)",
                            lineno,
                            self._feedback_path,
                            type(data).__name__,
                        )
                        continue
                    known = {f.name for f in dataclasses.fields(Feedback)}
                    try:
                        entries.append(Feedback(**{k: v for k, v in data.items() if k in known}))
                    except TypeError as exc:
                        logger.warning(
                            "Skipping malformed Feedback on line %d of %s: %s",
                            lineno,
                            self._feedback_path,
                            exc,
                        )
                        continue
        except OSError as exc:
            raise MemoryStoreError(f"Failed to read feedback: {exc}") from exc

        return entries

    def persist(self) -> None:
        """No-op — writes are flushed immediately in :meth:`append_feedback`.

        Present for interface symmetry so callers can call ``persist()``
        without needing to know about the underlying implementation.

        Raises
        ------
        MemoryStoreError
            If not mounted.
        """
        self._require_mounted()

    def clear(self) -> None:
        """Truncate the feedback file (creates it empty if it does not exist).

        Raises
        ------
        MemoryStoreError
            If not mounted or on I/O error.
        """
        self._require_mounted()
        try:
            self._feedback_path.write_text("", encoding="utf-8")  # type: ignore[union-attr]
        except OSError as exc:
            raise MemoryStoreError(
                f"Failed to clear feedback file: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internals

    def _require_mounted(self) -> None:
        """Raise :exc:`MemoryStoreError` if the store has not been mounted."""
        if self._feedback_path is None:
            raise MemoryStoreError(
                "MemoryStore has not been mounted; call mount() first"
            )

    @property
    def memory_dir(self) -> Path:
        """Absolute path to the memory directory.

        Returns
        -------
        Path
            The directory that holds the feedback file.

        Raises
        ------
        MemoryStoreError
            If the store has not been mounted yet.
        """
        self._require_mounted()
        return self._memory_dir  # type: ignore[return-value]
