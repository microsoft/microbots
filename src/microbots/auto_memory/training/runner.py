"""Run repository training with a reading bot and persistent memory tool."""

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from microbots.bot.ReadingBot import ReadingBot
from microbots.tools.tool_definitions.memory_tool import MemoryTool
from microbots.MicroBot import BotRunResult

logger = logging.getLogger(__name__)

_INSTRUCTIONS_PATH = Path(__file__).parent / "training_instructions.md"

# Matches SCP-style SSH remotes, e.g. "git@github.com:org/repo" or
# "git@github.com:org/repo.git". urlparse() alone can't detect these since
# they have no scheme, and they don't always end in ".git".
_SCP_STYLE_RE = re.compile(r"^[\w.\-]+@[\w.\-]+:")


def _is_git_url(repo: str) -> bool:
    """Determine whether a repository reference looks like a Git remote.

    Parameters
    ----------
    repo : str
        Repository path or URL.

    Returns
    -------
    bool
        ``True`` when the reference looks like a Git remote.
    """
    parsed = urlparse(repo)
    return (
        parsed.scheme in ("http", "https", "git", "ssh")
        or repo.endswith(".git")
        or bool(_SCP_STYLE_RE.match(repo))
    )

def _prepare_source_dir(repo: str, workdir: Path) -> Path:
    """Ensure a local directory exists for the agent to read from.

    Parameters
    ----------
    repo : str
        Local repository path or Git URL.
    workdir : pathlib.Path
        Working directory in which a remote repository can be cloned.

    Returns
    -------
    pathlib.Path
        Existing local repository path or the path to the cloned repository.
    """
    if not _is_git_url(repo):
        return Path(repo)

    dest = workdir / "source"
    if dest.exists():
        return dest  # reuse existing clone across iterations

    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo, str(dest)],
        check=True,
    )
    return dest


def run_training(
    repo_path: str,
    feedback: str,
    memory_dir: str,
    model: str,
    max_iterations: int = 20,
    timeout_in_seconds: int = 600,
) -> BotRunResult:
    """Run one training pass over a repository and update its memory.

    Parameters
    ----------
    repo_path : str
        Local repository path or Git URL to learn from.
    feedback : str
        Optional feedback to include in the training prompt.
    memory_dir : str
        Directory in which the memory tool stores its memory.
    model : str
        Model identifier used by the reading bot.
    max_iterations : int, default=20
        Maximum number of bot iterations.
    timeout_in_seconds : int, default=600
        Maximum duration of the bot run in seconds.

    Returns
    -------
    microbots.MicroBot.BotRunResult
        Result of the training bot run.
    """

    workdir = Path(tempfile.mkdtemp(prefix="training_workdir_"))
    try:
        source_dir = _prepare_source_dir(repo_path, workdir)

        instructions = _INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        feedback_section = feedback.strip() or "No feedback provided for this run."
        prompt = f"{instructions}\n\n## Feedback\n{feedback_section}\n"

        bot = ReadingBot(
            model=model,
            folder_to_mount=str(source_dir),
            additional_tools=[MemoryTool(memory_dir=memory_dir)],
        )

        return bot.run(
            prompt,
            max_iterations=max_iterations,
            timeout_in_seconds=timeout_in_seconds,
        )
    finally:
        # Only remove workdir when we actually cloned into it; a local
        # repo_path is used directly and must never be deleted here.
        if _is_git_url(repo_path):
            logger.info("Cleaning up training workdir %s", workdir)
            shutil.rmtree(workdir, ignore_errors=True)