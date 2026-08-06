"""Source specification for a training run.

A training run needs a local directory to mount into the bot's sandbox.
The source of that directory can be:

* ``type: "path"`` — an existing directory on disk. Used as-is.
* ``type: "git"``  — a git URL that is cloned (or fetched + checked out)
  into a local destination before the run starts.

The nested YAML shape is::

    source:
      type: path
      path: /some/local/dir

or::

    source:
      type: git
      url: https://github.com/foo/bar.git
      ref: main            # optional branch / tag / commit
      cache_dir: /some/dir # optional; default is <workdir>/source/

Legacy top-level ``source_path: <dir>`` is still accepted by
:meth:`TrainingConfig.load_from_yaml` and is normalised into a
``TrainingSource(type="path", path=...)``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any

from microbots.auto_memory.errors import ConfigError

logger = getLogger(__name__)

VALID_TYPES = ("path", "git")

# Recognises the URL shapes we accept as ``type: git``. We only auto-detect
# from a bare string in the legacy ``source_path`` field; the nested form
# uses an explicit ``type:`` so no detection is needed.
_GIT_URL_RE = re.compile(
    r"""^(
        https?://           # http://, https://
        | git://            # git://
        | ssh://            # ssh://
        | git@[^:]+:        # git@host:path
    )""",
    re.VERBOSE,
)


def looks_like_git_url(value: str) -> bool:
    """Check whether a value looks like a git remote URL.

    Parameters
    ----------
    value : str
        Candidate source value.

    Returns
    -------
    bool
        Whether the value has a recognized git URL form.
    """
    if not isinstance(value, str):
        return False
    if _GIT_URL_RE.match(value):
        return True
    return value.endswith(".git")


@dataclass
class TrainingSource:
    """Where the training run's source directory comes from.

    Attributes
    ----------
    type : str
        ``"path"`` for a local directory, ``"git"`` for a remote repo.
    path : Path | None
        For ``type="path"``: the existing local directory (required).
        For ``type="git"``: optional explicit clone destination; if unset,
        the loop uses ``<workdir>/source/`` at materialization time.
    url : str | None
        Git remote URL. Required when ``type="git"``, ignored otherwise.
    ref : str | None
        Branch, tag, or commit to check out after cloning. Ignored for
        ``type="path"``.
    cache_dir : Path | None
        Alternative name for ``path`` used only with ``type="git"``. Set
        this to reuse a clone across runs; leave unset for a fresh clone
        under the training workdir.
    """

    type: str = "path"
    path: Path | None = None
    url: str | None = None
    ref: str | None = None
    cache_dir: Path | None = None

    # ------------------------------------------------------------------
    # Constructors

    @classmethod
    def from_mapping(cls, data: Any, *, base_dir: Path) -> "TrainingSource":
        """Build a :class:`TrainingSource` from a YAML mapping.

        Parameters
        ----------
        data : Any
            Value parsed from the YAML ``source:`` key. Must be a mapping.
        base_dir : Path
            Directory used to resolve any relative ``path`` / ``cache_dir``
            entries (typically the YAML file's directory).

        Returns
        -------
        TrainingSource
            Parsed source specification.
        """
        if not isinstance(data, dict):
            raise ConfigError(
                "'source' must be a mapping with a 'type' key, "
                f"got {type(data).__name__}"
            )

        stype = str(data.get("type", "")).strip()
        if stype not in VALID_TYPES:
            raise ConfigError(
                f"'source.type' must be one of {VALID_TYPES}, got '{stype}'"
            )

        def _resolve(p: Any) -> Path | None:
            """Resolve an optional source path relative to ``base_dir``.

            Parameters
            ----------
            p : Any
                Optional configured path value.

            Returns
            -------
            Path | None
                Resolved path, or ``None`` when no value was provided.
            """
            if p is None:
                return None
            path = Path(p)
            return path if path.is_absolute() else (base_dir / path).resolve()

        return cls(
            type=stype,
            path=_resolve(data.get("path")),
            url=(str(data["url"]) if data.get("url") is not None else None),
            ref=(str(data["ref"]) if data.get("ref") is not None else None),
            cache_dir=_resolve(data.get("cache_dir")),
        )

    @classmethod
    def from_legacy_source_path(
        cls, value: str | Path, *, base_dir: Path | None = None
    ) -> "TrainingSource":
        """Wrap the legacy ``source_path`` value into a :class:`TrainingSource`.

        Auto-detects git URLs so an existing config that puts a URL in
        ``source_path`` keeps working.

        Parameters
        ----------
        value : str | Path
            Legacy local path or git URL value.
        base_dir : Path | None, optional
            Directory used to resolve a relative local path.

        Returns
        -------
        TrainingSource
            Normalized source specification.
        """
        raw = str(value)
        if looks_like_git_url(raw):
            return cls(type="git", url=raw)

        path = Path(value)
        if not path.is_absolute() and base_dir is not None:
            path = (base_dir / path).resolve()
        return cls(type="path", path=path)

    # ------------------------------------------------------------------
    # Validation

    def validate(self) -> None:
        """Validate the spec. Cheap checks only — cloning is deferred."""
        if self.type == "path":
            if self.path is None:
                raise ConfigError("'source.path' is required when type='path'")
            if not self.path.exists() or not self.path.is_dir():
                raise ConfigError(
                    "'source.path' must be an existing directory, "
                    f"got {self.path}"
                )
        elif self.type == "git":
            if not self.url:
                raise ConfigError("'source.url' is required when type='git'")
            # ``path`` and ``cache_dir`` are optional; either may double as the
            # clone destination. If both are given, ``cache_dir`` wins because
            # it is the git-specific field.
        else:  # pragma: no cover — from_mapping / __post_init__ blocks this.
            raise ConfigError(f"Unknown source.type '{self.type}'")

    # ------------------------------------------------------------------
    # Materialization

    def materialize(self, default_dest: Path) -> Path:
        """Return a local directory ready to be mounted into the sandbox.

        For ``type="path"`` this is a no-op returning :attr:`path`. For
        ``type="git"`` this clones (or fetches + resets) into either
        :attr:`cache_dir`, :attr:`path`, or ``default_dest``.

        Parameters
        ----------
        default_dest : Path
            Fallback clone destination when neither ``cache_dir`` nor
            ``path`` is set. Typically ``<workdir>/source``.

        Returns
        -------
        Path
            The local, on-disk source directory.
        """
        if self.type == "path":
            assert self.path is not None  # guarded by validate()
            return self.path

        assert self.type == "git" and self.url  # guarded by validate()
        dest = self.cache_dir or self.path or default_dest
        dest = dest.resolve()

        if _is_existing_git_checkout(dest):
            logger.info("TrainingSource: refreshing existing git checkout at %s", dest)
            _git_fetch_and_checkout(dest, url=self.url, ref=self.ref)
        else:
            if dest.exists() and any(dest.iterdir()):
                raise ConfigError(
                    f"Git clone destination {dest} exists and is not empty "
                    "(and is not an existing git checkout); refusing to clobber it."
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            logger.info("TrainingSource: cloning %s into %s", self.url, dest)
            _git_clone(url=self.url, dest=dest, ref=self.ref)

        # Cache the resolved local path so downstream code / metadata sees it.
        self.path = dest
        return dest

    # ------------------------------------------------------------------
    # Serialisation

    def to_meta(self) -> dict:
        """Build metadata for ``training_meta.json``.

        Returns
        -------
        dict
            JSON-serializable source metadata.
        """
        return {
            "type": self.type,
            "path": str(self.path) if self.path else None,
            "url": self.url,
            "ref": self.ref,
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
        }


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], *, cwd: Path | None = None) -> None:
    """Run a git subcommand, raising :class:`ConfigError` on failure.

    Parameters
    ----------
    args : list[str]
        Git arguments following the executable name.
    cwd : Path | None, optional
        Working directory for the command.
    """
    cmd = ["git", *args]
    logger.debug("TrainingSource: running %s (cwd=%s)", " ".join(cmd), cwd)
    try:
        subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ConfigError(
            "'git' executable not found on PATH; required for type='git' sources"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ConfigError(
            f"git {' '.join(args)} failed (exit {exc.returncode}): {stderr}"
        ) from exc


def _is_existing_git_checkout(dest: Path) -> bool:
    """Check whether a destination contains a git checkout.

    Parameters
    ----------
    dest : Path
        Candidate checkout directory.

    Returns
    -------
    bool
        Whether the destination and its ``.git`` entry exist.
    """
    return dest.exists() and (dest / ".git").exists()


def _git_clone(*, url: str, dest: Path, ref: str | None) -> None:
    """Clone a git source and optionally check out a requested ref.

    Parameters
    ----------
    url : str
        Remote repository URL.
    dest : Path
        Local clone destination.
    ref : str | None
        Optional branch, tag, or commit to check out.
    """
    args = ["clone", url, str(dest)]
    if ref:
        # ``--branch`` accepts branches or tags. Commits still need a
        # follow-up checkout below.
        args[1:1] = ["--branch", ref]
    try:
        _run_git(args)
    except ConfigError:
        # A commit SHA isn't a valid --branch target; retry without it and
        # check out the SHA after the clone.
        if not ref:
            raise
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        _run_git(["clone", url, str(dest)])
        _run_git(["checkout", ref], cwd=dest)


def _git_fetch_and_checkout(dest: Path, *, url: str, ref: str | None) -> None:
    """Refresh an existing checkout from its configured remote and ref.

    Parameters
    ----------
    dest : Path
        Existing local checkout.
    url : str
        Remote repository URL to configure as ``origin``.
    ref : str | None
        Optional branch, tag, or commit to check out.
    """
    # Point origin at the requested URL in case it changed since the last run.
    _run_git(["remote", "set-url", "origin", url], cwd=dest)
    _run_git(["fetch", "--prune", "origin"], cwd=dest)
    if ref:
        _run_git(["checkout", ref], cwd=dest)
        # For branches, fast-forward to the fetched tip. Ignored (harmless
        # error) for tags / detached HEADs by wrapping in a try.
        try:
            _run_git(["merge", "--ff-only", f"origin/{ref}"], cwd=dest)
        except ConfigError:
            pass
