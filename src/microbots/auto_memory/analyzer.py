"""Failure analysis utilities that convert callback results into structured feedback."""

from __future__ import annotations

from pathlib import Path

from microbots.auto_memory.callbacks import CallbackResult
from microbots.auto_memory.data_models import Feedback

# Maximum bytes read from a log tail when building root-cause snippets.
_MAX_LOG_BYTES = 4096


def analyze_failure(
    callback_results: list[CallbackResult],
    candidate_path: Path,
    iteration_idx: int,
) -> Feedback:
    """Produce a :class:`~microbots.auto_memory.data_models.Feedback` from callback results.

    Inspects every :class:`~microbots.auto_memory.callbacks.CallbackResult`
    and assembles a structured failure report that the agent can read on
    the next iteration.

    Parameters
    ----------
    callback_results : list[CallbackResult]
        Results returned by
        :meth:`~microbots.auto_memory.callbacks.ShellCallbackRunner.run_all`.
    candidate_path : Path
        Path to the candidate output for this iteration.  Reserved for
        future use (e.g. static analysis); not read directly at present.
    iteration_idx : int
        Zero-based index of the iteration that produced these results.

    Returns
    -------
    Feedback
        Structured summary with ``validator_failures``, ``root_causes``,
        ``suggested_actions``, and a human-readable ``summary`` string.
    """
    failed = [r for r in callback_results if not r.passed]

    validator_failures: list[str] = [r.spec.name for r in failed]
    root_causes: list[str] = []
    suggested_actions: list[str] = []

    for result in failed:
        if result.timed_out:
            root_causes.append(
                f"{result.spec.name}: timed out after {result.spec.timeout_s}s"
            )
            suggested_actions.append(
                f"Reduce runtime of {result.spec.name!r} or increase its timeout."
            )
        else:
            log_snippet = _read_tail(result.stderr_path) or _read_tail(result.stdout_path)
            if log_snippet:
                root_causes.append(f"{result.spec.name}: {log_snippet[:200]}")
            else:
                root_causes.append(
                    f"{result.spec.name}: exited with code {result.return_code}"
                    f" (expected {result.spec.expected_return_code})"
                )

    if failed:
        names = ", ".join(validator_failures)
        summary = f"{len(failed)} of {len(callback_results)} callback(s) failed: {names}"
    else:
        summary = "All callbacks passed."

    return Feedback(
        iteration_idx=iteration_idx,
        summary=summary,
        root_causes=root_causes,
        validator_failures=validator_failures,
        suggested_actions=suggested_actions,
    )


def _read_tail(path: Path, max_bytes: int = _MAX_LOG_BYTES) -> str:
    """Return the last *max_bytes* of *path* as a stripped string, or ``''`` if missing.

    Parameters
    ----------
    path : Path
        File to read from.
    max_bytes : int, optional
        Maximum number of bytes to read from the end of the file.

    Returns
    -------
    str
        Decoded and stripped tail of the file, or an empty string if the
        file cannot be opened.
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""
