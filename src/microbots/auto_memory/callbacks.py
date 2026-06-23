"""Callback runners that execute validation commands against candidate outputs."""

from __future__ import annotations

import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.data_models import CallbackSpec
from microbots.auto_memory.errors import CallbackError

logger = getLogger(__name__)


@dataclass
class CallbackResult:
    """Outcome of running a single callback."""

    spec: CallbackSpec
    return_code: int
    stdout_path: Path
    stderr_path: Path
    passed: bool
    timed_out: bool = False
    duration_s: float = field(default=0.0)


class CallbackRunner(ABC):
    """Abstract base: execute a list of callbacks and return their results."""

    @abstractmethod
    def run_all(
        self,
        specs: list[CallbackSpec],
        logs_dir: Path,
        candidate_path: Path,
    ) -> list[CallbackResult]:
        """Run every spec and return one :class:`CallbackResult` per spec.

        Parameters
        ----------
        specs : list[CallbackSpec]
            Ordered list of callbacks to execute.
        logs_dir : Path
            Directory where stdout/stderr files are written.
        candidate_path : Path
            Path to the candidate output; exposed as ``$CANDIDATE`` in
            the shell environment.

        Returns
        -------
        list[CallbackResult]
            One result per spec, in the same order as *specs*.
        """


class ShellCallbackRunner(CallbackRunner):
    """Run each callback as a shell subprocess.

    The environment variable ``$CANDIDATE`` is set to ``str(candidate_path)``
    before each command is executed.  stdout and stderr are redirected to::

        <logs_dir>/<callback_name>.stdout
        <logs_dir>/<callback_name>.stderr

    A callback whose process exits with a return code other than
    ``spec.expected_return_code``, or that exceeds ``spec.timeout_s``, is
    recorded as *not passed*.

    Raises
    ------
    CallbackError
        If a callback process cannot be spawned (e.g. permission error).
        A non-zero exit code is *not* treated as an error — it is captured
        in :attr:`CallbackResult.passed`.
    """

    def run_all(
        self,
        specs: list[CallbackSpec],
        logs_dir: Path,
        candidate_path: Path,
    ) -> list[CallbackResult]:
        """Run every spec sequentially and return their results.

        Parameters
        ----------
        specs : list[CallbackSpec]
            Ordered list of callbacks to execute.
        logs_dir : Path
            Directory where stdout/stderr files are written.
        candidate_path : Path
            Path to the candidate output; exposed as ``$CANDIDATE`` in
            the shell environment.

        Returns
        -------
        list[CallbackResult]
            One result per spec, in the same order as *specs*.
        """
        return [self._run_one(spec, logs_dir, candidate_path) for spec in specs]

    # ------------------------------------------------------------------
    # Internal

    def _run_one(
        self,
        spec: CallbackSpec,
        logs_dir: Path,
        candidate_path: Path,
    ) -> CallbackResult:
        """Execute a single callback spec as a subprocess.

        Parameters
        ----------
        spec : CallbackSpec
            The callback definition to run.
        logs_dir : Path
            Directory where stdout/stderr files are written.
        candidate_path : Path
            Path to the candidate output; exposed as ``$CANDIDATE`` in
            the shell environment.

        Returns
        -------
        CallbackResult
            The outcome of running this callback.
        """
        stdout_path = logs_dir / f"{spec.name}.stdout"
        stderr_path = logs_dir / f"{spec.name}.stderr"

        env = os.environ.copy()
        env["CANDIDATE"] = str(candidate_path)

        return_code: int = -1
        timed_out: bool = False
        start = time.monotonic()

        try:
            with (
                stdout_path.open("w", encoding="utf-8") as out_fh,
                stderr_path.open("w", encoding="utf-8") as err_fh,
            ):
                # Security note: spec.command is intentionally run with
                # shell=True for developer convenience (supports pipes,
                # redirects, etc.).  This runner assumes configs are loaded
                # from trusted local files only.  Do NOT use with configs
                # sourced from untrusted input.
                proc = subprocess.run(
                    spec.command,
                    shell=True,
                    stdout=out_fh,
                    stderr=err_fh,
                    env=env,
                    timeout=spec.timeout_s,
                )
                return_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            return_code = -1
            logger.warning(
                "Callback %r timed out after %ds", spec.name, spec.timeout_s
            )
        except OSError as exc:
            raise CallbackError(
                f"Failed to execute callback {spec.name!r}: {exc}"
            ) from exc

        duration_s = time.monotonic() - start
        passed = (not timed_out) and (return_code == spec.expected_return_code)

        return CallbackResult(
            spec=spec,
            return_code=return_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            passed=passed,
            timed_out=timed_out,
            duration_s=duration_s,
        )
