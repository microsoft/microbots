"""Unit tests for microbots.auto_memory.training.runner.

All external dependencies (subprocess/git, ReadingBot, MemoryTool) are
mocked so these tests run without Docker, network access, or an LLM.
The one exception is test_run_training_end_to_end, which is a real
integration test (marked accordingly) that exercises Docker and a live
model deployment.
"""

from pathlib import Path
from subprocess import CalledProcessError
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory.training.runner import (
    _is_git_url,
    _prepare_source_dir,
    run_training,
    run_training_loop,
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
        ("git@github.com:pytest-dev/pytest", True),  # SCP-style, no .git suffix
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


@pytest.mark.unit
def test_run_training_cleans_up_workdir_after_git_clone(tmp_path):
    """When repo_path is a git URL, the temp workdir it clones into should
    be removed once the run finishes."""
    memory_dir = tmp_path / "memory"
    repo_url = "https://github.com/pytest-dev/pytest.git"

    created_workdirs = []

    def fake_clone(cmd, check):
        # cmd = ["git", "clone", "--depth", "1", repo_url, dest]
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)

    mock_bot_instance = MagicMock()
    mock_bot_instance.run.return_value = BotRunResult(
        status=True, result="ok", error=None
    )

    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_workdirs.append(Path(path))
        return path

    with patch(
        "microbots.auto_memory.training.runner.subprocess.run",
        side_effect=fake_clone,
    ), patch(
        "microbots.auto_memory.training.runner.tempfile.mkdtemp",
        side_effect=tracking_mkdtemp,
    ), patch(
        "microbots.auto_memory.training.runner.ReadingBot",
        return_value=mock_bot_instance,
    ), patch("microbots.auto_memory.training.runner.MemoryTool"):
        run_training(
            repo_path=repo_url,
            feedback="",
            memory_dir=str(memory_dir),
            model="azure-openai/gpt-4o",
        )

    assert len(created_workdirs) == 1
    assert not created_workdirs[0].exists()


@pytest.mark.unit
def test_run_training_keeps_local_repo_untouched(tmp_path):
    """When repo_path is a local directory, it must never be deleted,
    even though the (unused) temp workdir is still cleaned up."""
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    (local_repo / "marker.txt").write_text("keep me")
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

    assert (local_repo / "marker.txt").exists()


# ---------------------------------------------------------------------------
# run_training_loop
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_training_loop_calls_run_training_n_times_with_same_memory_dir():
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch(
        "microbots.auto_memory.training.runner.run_training",
        return_value=fake_result,
    ) as mock_run_training:
        run_training_loop(
            repo_path="/some/repo",
            feedback="fb",
            memory_dir="/some/memory",
            model="azure-openai/gpt-4o",
            iterations=3,
        )

    assert mock_run_training.call_count == 3
    for call in mock_run_training.call_args_list:
        assert call.kwargs["memory_dir"] == "/some/memory"
        assert call.kwargs["feedback"] == "fb"
        assert call.kwargs["repo_path"] == "/some/repo"
        assert call.kwargs["model"] == "azure-openai/gpt-4o"


@pytest.mark.unit
def test_run_training_loop_returns_last_result():
    results = [
        BotRunResult(status=True, result="first", error=None),
        BotRunResult(status=False, result=None, error="second failed"),
        BotRunResult(status=True, result="third", error=None),
    ]

    with patch(
        "microbots.auto_memory.training.runner.run_training",
        side_effect=results,
    ):
        result = run_training_loop(
            repo_path="/some/repo",
            feedback="",
            memory_dir="/some/memory",
            model="azure-openai/gpt-4o",
            iterations=3,
        )

    assert result is results[-1]


@pytest.mark.unit
def test_run_training_loop_continues_after_a_failed_iteration():
    """A failure on iteration N must not stop iteration N+1 from running."""
    results = [
        BotRunResult(status=False, result=None, error="boom"),
        BotRunResult(status=True, result="ok", error=None),
    ]

    with patch(
        "microbots.auto_memory.training.runner.run_training",
        side_effect=results,
    ) as mock_run_training:
        result = run_training_loop(
            repo_path="/some/repo",
            feedback="",
            memory_dir="/some/memory",
            model="azure-openai/gpt-4o",
            iterations=2,
        )

    assert mock_run_training.call_count == 2
    assert result is results[-1]


@pytest.mark.unit
def test_run_training_loop_default_single_iteration():
    fake_result = BotRunResult(status=True, result="ok", error=None)

    with patch(
        "microbots.auto_memory.training.runner.run_training",
        return_value=fake_result,
    ) as mock_run_training:
        result = run_training_loop(
            repo_path="/some/repo",
            feedback="",
            memory_dir="/some/memory",
            model="azure-openai/gpt-4o",
        )

    mock_run_training.assert_called_once()
    assert result is fake_result
