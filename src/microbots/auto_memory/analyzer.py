"""Failure analysis that uses LogAnalysisBot to turn callback failures into feedback."""

from __future__ import annotations

import tempfile
from logging import getLogger
from pathlib import Path

from microbots.auto_memory.callbacks import CallbackResult
from microbots.auto_memory.data_models import Feedback
from microbots.bot.LogAnalysisBot import LogAnalysisBot

logger = getLogger(__name__)

# Per-stream tail cap when assembling the combined log fed to the LLM
# analyzer. Prevents pathological callback outputs (e.g. verbose pytest
# tracebacks or dumped fixtures) from blowing up model context / cost.
_LOG_TAIL_BYTES = 16 * 1024


def analyze_failure(
    callback_results: list[CallbackResult],
    candidate_path: Path,
    iteration_idx: int,
    *,
    analyzer_model: str,
    analyzer_max_iterations: int,
    analyzer_timeout_s: int,
) -> Feedback:
    """Produce a :class:`~microbots.auto_memory.data_models.Feedback` via LogAnalysisBot.

    Combines the stdout/stderr of every failed callback into a single log
    file and hands it to a fresh
    :class:`~microbots.bot.LogAnalysisBot.LogAnalysisBot` with the candidate
    directory mounted read-only. The bot's final narrative answer is stored
    as :attr:`Feedback.summary`; :attr:`Feedback.root_causes` is left empty
    on the success path because the LLM emits a single diagnosis rather
    than a discrete list.

    On no failures, returns a minimal ``All callbacks passed.`` feedback
    without invoking the bot. If the bot raises or fails to produce a
    result, :attr:`Feedback.summary` falls back to a short
    ``"<N> of <M> callback(s) failed: ..."`` string and
    :attr:`Feedback.root_causes` contains the analyzer error.

    In every non-passing case :attr:`Feedback.validator_failures` lists the
    names of the callbacks that did not pass.

    Parameters
    ----------
    callback_results : list[CallbackResult]
        Results returned by
        :meth:`~microbots.auto_memory.callbacks.ShellCallbackRunner.run_all`.
    candidate_path : Path
        Path to the candidate output for this iteration; mounted read-only
        into the bot so it can correlate log entries with source.
    iteration_idx : int
        Zero-based index of the iteration that produced these results.
    analyzer_model : str
        LiteLLM model identifier for :class:`~microbots.bot.LogAnalysisBot.LogAnalysisBot`.
    analyzer_max_iterations : int
        Maximum bot iterations to run.
    analyzer_timeout_s : int
        Bot timeout in seconds.

    Returns
    -------
    Feedback
        Structured summary with ``validator_failures``, ``root_causes``,
        and a human-readable ``summary`` string.
    """
    failed = [r for r in callback_results if not r.passed]
    validator_failures: list[str] = [r.spec.name for r in failed]

    if not failed:
        return Feedback(iteration_idx=iteration_idx, summary="All callbacks passed.")

    summary = (
        f"{len(failed)} of {len(callback_results)} callback(s) failed: "
        f"{', '.join(validator_failures)}"
    )

    # LogAnalysisBot needs a directory for its read-only mount.
    mount_folder = (
        candidate_path
        if candidate_path.exists() and candidate_path.is_dir()
        else candidate_path.parent
    )

    combined_log = _write_combined_log(failed)
    try:
        bot = LogAnalysisBot(
            model=analyzer_model,
            folder_to_mount=str(mount_folder),
        )
        bot_result = bot.run(
            file_name=str(combined_log),
            max_iterations=analyzer_max_iterations,
            timeout_in_seconds=analyzer_timeout_s,
        )
    except Exception as exc:
        logger.warning("LogAnalysisBot invocation failed: %s", exc, exc_info=True)
        return Feedback(
            iteration_idx=iteration_idx,
            summary=summary,
            validator_failures=validator_failures,
            root_causes=[f"LLM analyzer error: {exc}"],
        )
    finally:
        combined_log.unlink(missing_ok=True)

    if bot_result.status and bot_result.result:
        # The LLM produces one narrative diagnosis, not a list of causes;
        # store it as the summary and leave root_causes empty.
        return Feedback(
            iteration_idx=iteration_idx,
            summary=bot_result.result.strip(),
            validator_failures=validator_failures,
        )

    return Feedback(
        iteration_idx=iteration_idx,
        summary=summary,
        validator_failures=validator_failures,
        root_causes=[
            f"LLM analyzer did not produce a result: {bot_result.error or 'unknown'}"
        ],
    )


def _write_combined_log(failed: list[CallbackResult]) -> Path:
    """Write a temp log file combining every failed callback's stdout/stderr.

    Parameters
    ----------
    failed : list[CallbackResult]
        Results of the callbacks that did not pass.

    Returns
    -------
    Path
        Path to the newly created combined log file. Caller is responsible
        for deleting it.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as fh:
        for r in failed:
            fh.write(f"\n===== callback: {r.spec.name} =====\n")
            fh.write(
                f"return_code={r.return_code} "
                f"expected={r.spec.expected_return_code} "
                f"timed_out={r.timed_out} "
                f"duration_s={r.duration_s:.2f}\n"
            )
            fh.write("--- stderr ---\n")
            fh.write(_safe_read(r.stderr_path))
            fh.write("\n--- stdout ---\n")
            fh.write(_safe_read(r.stdout_path))
            fh.write("\n")
        return Path(fh.name)


def _safe_read(path: Path, max_bytes: int = _LOG_TAIL_BYTES) -> str:
    """Return the tail of *path*'s text content, or a placeholder on I/O error.

    Only the last ``max_bytes`` bytes are read to bound memory usage and the
    downstream LLM analyzer context. When the file exceeds that cap a
    ``"<truncated: showing last N bytes of M>\\n"`` marker is prepended so
    the model knows the view is partial.

    Parameters
    ----------
    path : Path
        Filesystem path to read.
    max_bytes : int, optional
        Maximum number of trailing bytes to return. Defaults to
        ``_LOG_TAIL_BYTES``. A value ``<= 0`` disables the cap.

    Returns
    -------
    str
        The (possibly truncated) file contents decoded as UTF-8 (invalid
        bytes replaced), or ``"<log unavailable>"`` if the file cannot be
        read.
    """
    try:
        if max_bytes <= 0:
            data = path.read_bytes()
            truncated = False
            total = len(data)
        else:
            size = path.stat().st_size
            with path.open("rb") as fh:
                if size > max_bytes:
                    fh.seek(size - max_bytes)
                    truncated = True
                else:
                    truncated = False
                data = fh.read()
            total = size
    except OSError:
        return "<log unavailable>"

    text = data.decode("utf-8", errors="replace")
    if truncated:
        return f"<truncated: showing last {len(data)} bytes of {total}>\n{text}"
    return text
