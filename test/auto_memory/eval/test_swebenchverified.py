"""Unit tests for microbots.auto_memory.eval.swebenchverified."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src/")))

from microbots.auto_memory.eval.swebenchverified import (
    SweBenchInstance,
    SweBenchVerifiedTask,
    load_instance_using_id,
    load_instances_of_repo,
)
from microbots.auto_memory.task import CallbackResult

MODULE = "microbots.auto_memory.eval.swebenchverified"


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


# ---------------------------------------------------------------------------
# SweBenchVerifiedTask.run
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_calls_setup_build_prompt_check_teardown_in_order(mock_bot_cls, mock_memory_tool):
    from microbots.MicroBot import BotRunResult

    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="agent did stuff", error=None)
    mock_bot_cls.return_value = mock_bot

    task = SweBenchVerifiedTask(_instance())
    calls = []
    task.setup = lambda repo_path: calls.append(("setup", repo_path))
    task.build_prompt = lambda repo_path: "do the task"
    task.check = lambda repo_path, agent_output, log_path: (
        calls.append(("check", repo_path, agent_output, log_path))
        or CallbackResult(passed=True, reason="ok")
    )
    task.teardown = lambda repo_path: calls.append(("teardown", repo_path))

    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert calls[0] == ("setup", "/repo")
    assert calls[1] == ("check", "/repo", "agent did stuff", outcome.log_path)
    assert calls[2] == ("teardown", "/repo")
    assert outcome.passed is True
    assert outcome.output == "agent did stuff"


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_creates_log_file_before_check_is_called(mock_bot_cls, mock_memory_tool):
    from microbots.MicroBot import BotRunResult

    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = SweBenchVerifiedTask(_instance())
    task.setup = lambda repo_path: None
    task.build_prompt = lambda repo_path: "do the task"
    task.teardown = lambda repo_path: None
    seen_log_exists = {}

    def _check(repo_path, agent_output, log_path):
        seen_log_exists["exists"] = os.path.exists(log_path)
        return CallbackResult(passed=True, reason="ok")

    task.check = _check

    task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert seen_log_exists["exists"] is True


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_skips_check_when_bot_status_is_false(mock_bot_cls, mock_memory_tool):
    from microbots.MicroBot import BotRunResult

    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=False, result=None, error="bot crashed")
    mock_bot_cls.return_value = mock_bot

    task = SweBenchVerifiedTask(_instance())
    check_calls = []
    task.setup = lambda repo_path: None
    task.build_prompt = lambda repo_path: "do the task"
    task.check = lambda *a: check_calls.append(a)
    task.teardown = lambda repo_path: None

    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert check_calls == []
    assert outcome.passed is False
    assert "bot crashed" in outcome.result.reason


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_converts_build_prompt_exception_to_failed_outcome(mock_bot_cls, mock_memory_tool):
    task = SweBenchVerifiedTask(_instance())
    task.setup = lambda repo_path: None
    task.teardown = lambda repo_path: None

    def _build_prompt(repo_path):
        raise ValueError("bad prompt")

    task.build_prompt = _build_prompt

    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert outcome.passed is False
    assert "bad prompt" in outcome.result.reason
    with open(outcome.log_path) as f:
        assert "bad prompt" in f.read()


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_converts_check_exception_to_failed_outcome(mock_bot_cls, mock_memory_tool):
    from microbots.MicroBot import BotRunResult

    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = SweBenchVerifiedTask(_instance())
    task.setup = lambda repo_path: None
    task.build_prompt = lambda repo_path: "do the task"
    task.teardown = lambda repo_path: None

    def _check(repo_path, agent_output, log_path):
        raise RuntimeError("check exploded")

    task.check = _check

    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert outcome.passed is False
    assert "check exploded" in outcome.result.reason


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_still_calls_teardown_when_body_raises(mock_bot_cls, mock_memory_tool):
    mock_bot_cls.side_effect = RuntimeError("bot construction failed")

    task = SweBenchVerifiedTask(_instance())
    teardown_calls = []
    task.setup = lambda repo_path: None
    task.build_prompt = lambda repo_path: "do the task"
    task.teardown = lambda repo_path: teardown_calls.append(repo_path)

    task.run("/repo", "/memory", "azure-openai/gpt-4o")

    assert teardown_calls == ["/repo"]


@pytest.mark.unit
@patch(f"{MODULE}.MemoryTool")
@patch(f"{MODULE}.WritingBot")
def test_run_teardown_exception_does_not_clobber_returned_outcome(mock_bot_cls, mock_memory_tool):
    from microbots.MicroBot import BotRunResult

    mock_bot = MagicMock()
    mock_bot.run.return_value = BotRunResult(status=True, result="output", error=None)
    mock_bot_cls.return_value = mock_bot

    task = SweBenchVerifiedTask(_instance())
    task.setup = lambda repo_path: None
    task.build_prompt = lambda repo_path: "do the task"
    task.check = lambda repo_path, agent_output, log_path: CallbackResult(passed=True, reason="ok")

    def _teardown(repo_path):
        raise RuntimeError("teardown boom")

    task.teardown = _teardown

    outcome = task.run("/repo", "/memory", "azure-openai/gpt-4o")

    # teardown() raised, but the already-computed EvalOutcome must still be returned
    assert outcome.passed is True



# ---------------------------------------------------------------------------
# SweBenchVerifiedTask.add_cli_args / from_cli_args
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_add_cli_args_registers_instance_id_and_repo_flags():
    import argparse

    parser = argparse.ArgumentParser()
    SweBenchVerifiedTask.add_cli_args(parser)

    args = parser.parse_args(["--instance-id", "django__django-1", "--swebench-repo", "django/django"])
    assert args.instance_id == "django__django-1"
    assert args.swebench_repo == "django/django"


@pytest.mark.unit
@patch(f"{MODULE}.load_instance_using_id")
def test_from_cli_args_uses_instance_id_when_given(mock_load_instance_using_id):
    mock_load_instance_using_id.return_value = _instance()
    args = MagicMock(instance_id="django__django-1", swebench_repo=None)

    tasks = SweBenchVerifiedTask.from_cli_args(args)

    mock_load_instance_using_id.assert_called_once_with("django__django-1")
    assert len(tasks) == 1
    assert isinstance(tasks[0], SweBenchVerifiedTask)
    assert tasks[0].instance == _instance()


@pytest.mark.unit
@patch(f"{MODULE}.load_instances_of_repo")
def test_from_cli_args_falls_back_to_repo_filter_when_no_instance_id(mock_load_instances_of_repo):
    mock_load_instances_of_repo.return_value = [_instance(), _instance()]
    args = MagicMock(instance_id=None, swebench_repo="django/django")

    tasks = SweBenchVerifiedTask.from_cli_args(args)

    mock_load_instances_of_repo.assert_called_once_with(repo="django/django")
    assert len(tasks) == 2
    assert all(isinstance(t, SweBenchVerifiedTask) for t in tasks)


@pytest.mark.unit
@patch(f"{MODULE}.load_instances_of_repo")
def test_from_cli_args_handles_missing_attrs_gracefully(mock_load_instances_of_repo):
    """Namespace without instance_id/swebench_repo attrs at all (not just None)."""
    mock_load_instances_of_repo.return_value = [_instance()]

    class _EmptyArgs:
        pass

    tasks = SweBenchVerifiedTask.from_cli_args(_EmptyArgs())

    mock_load_instances_of_repo.assert_called_once_with(repo=None)
    assert len(tasks) == 1
