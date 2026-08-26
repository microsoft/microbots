"""Unit tests for microbots.auto_memory.eval_swebenchverified.eval."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src/")))

from microbots.auto_memory.eval_swebenchverified.eval import (
    SweBenchInstance,
    SweBenchVerifiedTask,
    load_instance_using_id,
    load_instances_of_repo,
)

MODULE = "microbots.auto_memory.eval_swebenchverified.eval"


def _fake_rows():
    return [
        {
            "instance_id": "django__django-1",
            "repo": "django/django",
            "base_commit": "abc123",
            "problem_statement": "fix bug 1",
        },
        {
            "instance_id": "astropy__astropy-1",
            "repo": "astropy/astropy",
            "base_commit": "def456",
            "problem_statement": "fix bug 2",
        },
        {
            "instance_id": "django__django-2",
            "repo": "django/django",
            "base_commit": "ghi789",
            "problem_statement": "fix bug 3",
        },
    ]


# ---------------------------------------------------------------------------
# load_instances_of_repo / load_instance_using_id
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch(f"{MODULE}.load_dataset")
def test_load_instances_of_repo_filters_by_repo(mock_load_dataset):
    mock_load_dataset.return_value = _fake_rows()

    instances = load_instances_of_repo(repo="django/django")

    assert [i.instance_id for i in instances] == ["django__django-1", "django__django-2"]
    assert all(isinstance(i, SweBenchInstance) for i in instances)


@pytest.mark.unit
@patch(f"{MODULE}.load_dataset")
def test_load_instances_of_repo_returns_all_when_repo_none(mock_load_dataset):
    mock_load_dataset.return_value = _fake_rows()

    instances = load_instances_of_repo(repo=None)

    assert len(instances) == 3


@pytest.mark.unit
@patch(f"{MODULE}.load_dataset")
def test_load_instance_using_id_returns_matching_instance(mock_load_dataset):
    mock_load_dataset.return_value = _fake_rows()

    instance = load_instance_using_id("astropy__astropy-1")

    assert instance.repo == "astropy/astropy"
    assert instance.problem_statement == "fix bug 2"


@pytest.mark.unit
@patch(f"{MODULE}.load_dataset")
def test_load_instance_using_id_raises_when_not_found(mock_load_dataset):
    mock_load_dataset.return_value = _fake_rows()

    with pytest.raises(ValueError, match="not found"):
        load_instance_using_id("does-not-exist")


# ---------------------------------------------------------------------------
# SweBenchVerifiedTask.setup / build_prompt / teardown
# ---------------------------------------------------------------------------

def _instance():
    return SweBenchInstance(
        instance_id="django__django-1",
        repo="django/django",
        base_commit="abc123",
        problem_statement="fix the bug",
    )


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_setup_clones_and_checks_out_base_commit(mock_run):
    task = SweBenchVerifiedTask(_instance())
    task.setup("/repo")

    clone_call, checkout_call = mock_run.call_args_list
    assert clone_call.args[0] == ["git", "clone", "https://github.com/django/django.git", "/repo"]
    assert checkout_call.args[0] == ["git", "checkout", "abc123"]
    assert checkout_call.kwargs["cwd"] == "/repo"


@pytest.mark.unit
def test_build_prompt_returns_problem_statement():
    task = SweBenchVerifiedTask(_instance())
    assert task.build_prompt("/repo") == "fix the bug"


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_teardown_removes_repo_path(mock_run):
    task = SweBenchVerifiedTask(_instance())
    task.teardown("/repo")

    mock_run.assert_called_once_with(["rm", "-rf", "/repo"], check=False)


# ---------------------------------------------------------------------------
# SweBenchVerifiedTask.check
# ---------------------------------------------------------------------------

def _make_fake_subprocess_run(resolved: bool, raise_on_harness: bool = False):
    """Build a subprocess.run stand-in that fakes git diff + the harness call."""

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "diff"]:
            return MagicMock(stdout="diff --git a/x.py b/x.py\n+fix", stderr="", returncode=0)
        if "swebench.harness.run_evaluation" in cmd:
            if raise_on_harness:
                raise RuntimeError("harness crashed")
            run_id = cmd[cmd.index("--run_id") + 1]
            report_dir = kwargs["cwd"]
            instance_id = cmd[cmd.index("--instance_ids") + 1]
            report = {"resolved_ids": [instance_id] if resolved else []}
            (Path(report_dir) / f"microbots-eval-agent.{run_id}.json").write_text(json.dumps(report))
            return MagicMock(stdout="harness ran\n", stderr="", returncode=0)
        return MagicMock(stdout="", stderr="", returncode=0)

    return _fake_run


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_check_passed_true_when_instance_in_resolved_ids(mock_run, tmp_path):
    mock_run.side_effect = _make_fake_subprocess_run(resolved=True)
    log_path = tmp_path / "check.log"
    log_path.write_text("")

    task = SweBenchVerifiedTask(_instance())
    result = task.check("/repo", "agent output", str(log_path))

    assert result.passed is True
    assert result.reason == "resolved"


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_check_passed_false_when_instance_not_in_resolved_ids(mock_run, tmp_path):
    mock_run.side_effect = _make_fake_subprocess_run(resolved=False)
    log_path = tmp_path / "check.log"
    log_path.write_text("")

    task = SweBenchVerifiedTask(_instance())
    result = task.check("/repo", "agent output", str(log_path))

    assert result.passed is False
    assert result.reason == "not resolved"


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_check_passed_false_when_report_file_never_written(mock_run, tmp_path):
    # harness call succeeds but never writes a report file (e.g. it errored internally)
    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "diff"]:
            return MagicMock(stdout="diff", stderr="", returncode=0)
        return MagicMock(stdout="", stderr="", returncode=1)

    mock_run.side_effect = _fake_run
    log_path = tmp_path / "check.log"
    log_path.write_text("")

    task = SweBenchVerifiedTask(_instance())
    result = task.check("/repo", "agent output", str(log_path))

    assert result.passed is False


@pytest.mark.unit
@patch(f"{MODULE}.subprocess.run")
def test_check_appends_to_log_file_without_truncating_existing_content(mock_run, tmp_path):
    mock_run.side_effect = _make_fake_subprocess_run(resolved=True)
    log_path = tmp_path / "check.log"
    log_path.write_text("Agent output:\nprevious content\n")

    task = SweBenchVerifiedTask(_instance())
    task.check("/repo", "agent output", str(log_path))

    content = log_path.read_text()
    assert "previous content" in content
    assert "harness ran" in content


@pytest.mark.unit
@patch(f"{MODULE}.shutil.rmtree")
@patch(f"{MODULE}.subprocess.run")
def test_check_cleans_up_pred_path_and_report_dir_on_success(mock_run, mock_rmtree, tmp_path):
    mock_run.side_effect = _make_fake_subprocess_run(resolved=True)
    log_path = tmp_path / "check.log"
    log_path.write_text("")

    task = SweBenchVerifiedTask(_instance())
    task.check("/repo", "agent output", str(log_path))

    mock_rmtree.assert_called_once()


@pytest.mark.unit
@patch(f"{MODULE}.shutil.rmtree")
@patch(f"{MODULE}.subprocess.run")
def test_check_cleans_up_even_when_harness_raises(mock_run, mock_rmtree, tmp_path):
    mock_run.side_effect = _make_fake_subprocess_run(resolved=True, raise_on_harness=True)
    log_path = tmp_path / "check.log"
    log_path.write_text("")

    task = SweBenchVerifiedTask(_instance())
    with pytest.raises(RuntimeError, match="harness crashed"):
        task.check("/repo", "agent output", str(log_path))

    mock_rmtree.assert_called_once()
