"""Unit tests for microbots.auto_memory.training.runner.

All external dependencies (subprocess/git, ReadingBot, MemoryTool) are
mocked so these tests run without Docker, network access, or an LLM.
The one exception is test_run_training_end_to_end, which is a real
integration test (marked accordingly) that exercises Docker and a live
model deployment.
"""

import os
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory.training.runner import (
    _is_git_url,
    _prepare_source_dir,
    run_training,
)
from microbots.MicroBot import BotRunResult


# ---------------------------------------------------------------------------
# _is_git_url
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "repo, expected",
    [
        ("https://github.com/pytest-dev/pytest.git", True),
        ("git@github.com:pytest-dev/pytest.git", True),
        ("ssh://git@github.com/pytest-dev/pytest.git", True),
        ("/home/user/some/local/repo", False),
        ("some-local-dir-without-scheme", False),
        ("relative/local/path.git", True),  # ends with .git -> treated as git
    ],
)
def test_is_git_url(repo, expected):
    assert _is_git_url(repo) is expected


# ---------------------------------------------------------------------------
# _prepare_source_dir
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_prepare_source_dir_local_path_passthrough(tmp_path):
    local_repo = tmp_path / "local_repo"
    local_repo.mkdir()

    with patch("microbots.auto_memory.training.runner.subprocess.run") as mock_run:
        result = _prepare_source_dir(str(local_repo), tmp_path / "workdir")

    assert result == Path(local_repo)
    mock_run.assert_not_called()


@pytest.mark.unit
def test_prepare_source_dir_clones_git_url(tmp_path):
    workdir = tmp_path / "workdir"
    repo_url = "https://github.com/pytest-dev/pytest.git"
    expected_dest = workdir / "source"

    with patch("microbots.auto_memory.training.runner.subprocess.run") as mock_run:
        result = _prepare_source_dir(repo_url, workdir)

    mock_run.assert_called_once_with(
        ["git", "clone", "--depth", "1", repo_url, str(expected_dest)],
        check=True,
    )
    assert result == expected_dest


@pytest.mark.unit
def test_prepare_source_dir_reuses_existing_clone(tmp_path):
    workdir = tmp_path / "workdir"
    dest = workdir / "source"
    dest.mkdir(parents=True)
    repo_url = "https://github.com/pytest-dev/pytest.git"

    with patch("microbots.auto_memory.training.runner.subprocess.run") as mock_run:
        result = _prepare_source_dir(repo_url, workdir)

    mock_run.assert_not_called()
    assert result == dest


@pytest.mark.unit
def test_prepare_source_dir_clone_failure_propagates(tmp_path):
    workdir = tmp_path / "workdir"
    repo_url = "https://github.com/pytest-dev/pytest.git"

    with patch(
        "microbots.auto_memory.training.runner.subprocess.run",
        side_effect=CalledProcessError(returncode=1, cmd=["git", "clone"]),
    ):
        with pytest.raises(CalledProcessError):
            _prepare_source_dir(repo_url, workdir)


# ---------------------------------------------------------------------------
# run_training
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_training_prompt_includes_feedback(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="Focus on error handling paths.",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    prompt_arg = mock_bot_instance.run.call_args.args[0]
    assert "Focus on error handling paths." in prompt_arg


@pytest.mark.unit
def test_run_training_prompt_handles_empty_feedback(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    prompt_arg = mock_bot_instance.run.call_args.args[0]
    assert "No feedback provided for this run." in prompt_arg


@pytest.mark.unit
def test_run_training_passes_correct_args_to_reading_bot(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )
    mock_memory_tool_instance = MagicMock()

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ) as mock_reading_bot, patch(
        "microbots.auto_memory.training.runner.MemoryTool",
        return_value=mock_memory_tool_instance,
    ) as mock_memory_tool:
        run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    mock_memory_tool.assert_called_once_with(memory_dir=str(memory_dir))

    _, kwargs = mock_reading_bot.call_args
    assert kwargs["model"] == "azure-openai/gpt-4o"
    assert kwargs["folder_to_mount"] == str(local_repo)
    assert kwargs["additional_tools"] == [mock_memory_tool_instance]


@pytest.mark.unit
def test_run_training_returns_bot_result(tmp_path):
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    memory_dir = tmp_path / "memory"

    expected_result = BotRunResult(status=True, result="done", error=None)
    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = expected_result

    with patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        result = run_training(
            repo_path=str(local_repo),
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    assert result is expected_result


# ---------------------------------------------------------------------------
# End-to-end integration test (real Docker + real LLM deployment required)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.docker
def test_run_training_end_to_end(test_repo, tmp_path):
    """Smoke-test the training flow against a small fixture repo.

    Requires Docker and a working model deployment (same env vars used by
    test/bot/test_reading_bot.py). This is a smoke test, not a
    completion test: max_iterations is intentionally kept small so it
    's fast to run locally. It only asserts the flow executes end-to-end
    (clone -> mount -> bot run) without asserting the agent reached
    task_done, since that may need more iterations than we want to spend
    here.
    """
    memory_dir = tmp_path / "memory"
    model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"

    result: BotRunResult = run_training(
        repo_path=str(test_repo),
        feedback="",
        memory_dir=str(memory_dir),
        model=model,
        max_iterations=8,
        timeout_in_seconds=600,
    )

    # Accept either a completed run, or a run that stopped only because it
    # hit the (intentionally low) iteration cap - both prove the flow works.
    acceptable_errors = (None, "Max iterations 8 reached")
    assert result.status or result.error in acceptable_errors, (
        f"Training run failed unexpectedly: {result.error}"
    )

    # With only 5 iterations the agent may not fully finish the task, but
    # it should still persist at least one memory file along the way.
    memory_files = [f for f in memory_dir.rglob("*") if f.is_file()]
    assert memory_files, (
        f"Expected at least one memory file under {memory_dir}, found none"
    )
