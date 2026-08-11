"""End-to-end tests for the auto_memory CLI entry point."""

from __future__ import annotations

import textwrap
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory import CallbackRunner, run_from_yaml
from microbots.auto_memory.callbacks import CallbackResult
from microbots.auto_memory.cli import main
from microbots.auto_memory.data_models import FinalStatus, IterationStatus
from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.orchestrator import RunSummary
from microbots.auto_memory.runners.base import AgentResult, AgentRunner
from microbots.MicroBot import BotRunResult

_MODEL = "azure-openai/gpt-4o"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_YAML = textwrap.dedent("""\
    task_definition: Write a hello message to /memories/hello.txt
    prompt_template: "Goal: {{ task }}"
    callbacks:
      - name: always_ok
        command: 'true'
    max_iterations: 1
    timeout_min: 1
    per_iteration_timeout: 30
""")

_TASK_YAML_FAILING = textwrap.dedent("""\
    task_definition: Write a hello message to /memories/hello.txt
    prompt_template: "Goal: {{ task }}"
    callbacks:
      - name: always_fail
        command: 'false'
    max_iterations: 2
    timeout_min: 1
    per_iteration_timeout: 30
""")


def _write_yaml(tmp_path: Path, content: str = _TASK_YAML) -> Path:
    p = tmp_path / "task.yml"
    p.write_text(content)
    return p


def _mock_writing_bot(status: bool = True, error: str | None = None):
    """Patch WritingBot to return a controllable BotRunResult."""
    bot_instance = MagicMock()
    bot_instance.run.return_value = BotRunResult(
        status=status,
        result="agent output" if status else None,
        error=error,
    )
    return patch(
        "microbots.auto_memory.runners.writing_bot_runner.WritingBot",
        return_value=bot_instance,
    ), bot_instance


def _mock_log_analysis_bot(result: str = "diagnosis narrative"):
    """Patch LogAnalysisBot so failure analysis never hits a real LLM endpoint."""
    bot_instance = MagicMock()
    bot_instance.run.return_value = BotRunResult(
        status=True, result=result, error=None
    )
    return patch(
        "microbots.auto_memory.analyzer.LogAnalysisBot",
        return_value=bot_instance,
    ), bot_instance


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunFromYamlEndToEnd:
    def test_yaml_supplies_model_and_default_workdir(self, tmp_path):
        yaml_path = _write_yaml(
            tmp_path,
            "model: azure-openai/gpt-4o\n" + _TASK_YAML,
        )
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(yaml_path, run_id="yaml-only")

        assert summary.final_status == FinalStatus.PASSED
        assert (tmp_path / ".auto-memory" / "runs" / "yaml-only").is_dir()

    def test_explicit_model_and_workdir_override_yaml(self, tmp_path):
        yaml_path = _write_yaml(
            tmp_path,
            "model: azure-openai/from-yaml\nworkdir: yaml-work\n" + _TASK_YAML,
        )
        bot_patch, _ = _mock_writing_bot()
        explicit_workdir = tmp_path / "explicit-work"

        with bot_patch as writing_bot, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            run_from_yaml(
                yaml_path,
                explicit_workdir,
                run_id="overrides",
                model=_MODEL,
            )

        assert writing_bot.call_args.kwargs["model"] == _MODEL
        assert (explicit_workdir / "runs" / "overrides").is_dir()
        assert not (tmp_path / "yaml-work").exists()

    def test_requires_model_in_yaml_or_argument(self, tmp_path):
        with pytest.raises(ConfigError, match="model is required"):
            run_from_yaml(_write_yaml(tmp_path))

    def test_returns_run_summary(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="t1", model=_MODEL
            )

        assert isinstance(summary, RunSummary)

    def test_final_status_passed_when_callbacks_pass(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="t2", model=_MODEL
            )

        assert summary.final_status == FinalStatus.PASSED
        assert summary.iterations_run == 1
        assert summary.error_message is None
        assert len(summary.iteration_records) == 1

    def test_uses_user_callback_runner(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        class PassingCallbacks(CallbackRunner):
            def run_all(self, specs, logs_dir, candidate_path):
                return [
                    CallbackResult(
                        spec=spec,
                        return_code=0,
                        stdout_path=logs_dir / f"{spec.name}.stdout",
                        stderr_path=logs_dir / f"{spec.name}.stderr",
                        passed=True,
                    )
                    for spec in specs
                ]

        callback_runner = PassingCallbacks()
        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ), patch(
            "microbots.auto_memory.cli.ShellCallbackRunner"
        ) as shell_callback_runner:
            summary = run_from_yaml(
                yaml_path,
                workdir,
                run_id="custom-callbacks",
                model=_MODEL,
                callback_runner=callback_runner,
            )

        assert summary.final_status == FinalStatus.PASSED
        shell_callback_runner.assert_not_called()

    def test_disk_layout_created(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            run_from_yaml(
                str(yaml_path), str(workdir), run_id="layout_run", model=_MODEL
            )

        run_dir = workdir / "runs" / "layout_run"
        assert run_dir.is_dir()
        assert (run_dir / "run_meta.json").is_file()
        assert (run_dir / "memory").is_dir()
        assert (run_dir / "memory" / "feedback.jsonl").is_file()
        assert (run_dir / "iterations" / "iter_00").is_dir()
        assert (run_dir / "iterations" / "iter_00" / "candidate").is_dir()
        assert (run_dir / "iterations" / "iter_00" / "logs").is_dir()

    def test_writing_bot_receives_memory_dir(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, bot_instance = _mock_writing_bot()

        with bot_patch as MockBot, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ) as MockMemoryTool:
            run_from_yaml(
                str(yaml_path), str(workdir), run_id="mem_run", model=_MODEL
            )

        expected_memory_dir = str(workdir / "runs" / "mem_run" / "memory")
        _, kwargs = MockBot.call_args
        assert kwargs["folder_to_mount"] == expected_memory_dir
        MockMemoryTool.assert_called_once_with(memory_dir=expected_memory_dir)

    def test_auto_generated_run_id(self, tmp_path):
        yaml_path = _write_yaml(tmp_path)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()

        with bot_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(str(yaml_path), str(workdir), model=_MODEL)

        assert summary.final_status == FinalStatus.PASSED
        runs_dir = workdir / "runs"
        children = [p for p in runs_dir.iterdir() if p.is_dir()]
        assert len(children) == 1
        assert children[0].name.startswith("run-")

    def test_failing_callbacks_persist_feedback_and_reach_limit(self, tmp_path):
        yaml_path = _write_yaml(tmp_path, _TASK_YAML_FAILING)
        workdir = tmp_path / "workdir"
        bot_patch, _ = _mock_writing_bot()
        analyzer_patch, _ = _mock_log_analysis_bot()

        with bot_patch, analyzer_patch, patch(
            "microbots.auto_memory.runners.writing_bot_runner.MemoryTool"
        ):
            summary = run_from_yaml(
                str(yaml_path), str(workdir), run_id="fail_run", model=_MODEL
            )

        assert summary.final_status == FinalStatus.LIMIT_REACHED
        assert summary.iterations_run == 2

        run_dir = workdir / "runs" / "fail_run"
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        assert feedback_file.is_file()
        lines = [ln for ln in feedback_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2
        assert (run_dir / "iterations" / "iter_01" / "candidate").is_dir()


@pytest.mark.unit
class TestAgentRunnerInjection:
    def test_uses_user_constructed_runner(self, tmp_path):
        class CustomRunner(AgentRunner):
            def __init__(self):
                self.calls = []

            def run(self, ctx, timeout_s):
                self.calls.append((ctx, timeout_s))
                return AgentResult(IterationStatus.PASSED, "done", None)

        runner = CustomRunner()
        summary = run_from_yaml(
            _write_yaml(tmp_path),
            tmp_path / "workdir",
            run_id="custom-runner",
            agent_runner=runner,
        )

        assert summary.final_status == FinalStatus.PASSED
        assert len(runner.calls) == 1
        assert runner.calls[0][0].task == "Goal: Write a hello message to /memories/hello.txt"

    def test_rejects_object_without_runner_protocol(self, tmp_path):
        with pytest.raises(ConfigError, match="AgentRunner"):
            run_from_yaml(
                _write_yaml(tmp_path),
                tmp_path / "workdir",
                agent_runner=object(),  # type: ignore[arg-type]
            )


@pytest.mark.unit
class TestMain:
    def test_runs_yaml_and_prints_summary(self, tmp_path, capsys):
        summary = RunSummary(
            final_status=FinalStatus.PASSED,
            iterations_run=2,
            elapsed_s=1.25,
        )
        yaml_path = tmp_path / "task.yaml"
        with patch(
            "microbots.auto_memory.cli.run_from_yaml", return_value=summary
        ) as run:
            assert main([str(yaml_path)]) == 0

        run.assert_called_once_with(
            yaml_path,
            workdir=None,
            run_id=None,
            model=None,
            external_memory_dir=None,
        )
        assert "auto-memory passed: iterations=2 elapsed=1.2s" in capsys.readouterr().out

    def test_overrides_yaml_options(self, tmp_path):
        summary = RunSummary(
            final_status=FinalStatus.PASSED,
            iterations_run=1,
        )
        yaml_path = tmp_path / "task.yaml"
        with patch(
            "microbots.auto_memory.cli.run_from_yaml", return_value=summary
        ) as run:
            assert main([
                str(yaml_path),
                "--model", _MODEL,
                "--workdir", "work",
                "--run-id", "fixed",
                "--external-memory-dir", "memory",
            ]) == 0

        assert run.call_args.kwargs == {
            "workdir": Path("work"),
            "run_id": "fixed",
            "model": _MODEL,
            "external_memory_dir": Path("memory"),
        }

    def test_reports_config_error(self, tmp_path, capsys):
        with patch(
            "microbots.auto_memory.cli.run_from_yaml",
            side_effect=ConfigError("bad task"),
        ):
            assert main([str(tmp_path / "task.yaml")]) == 2
        assert "config error: bad task" in capsys.readouterr().err

    def test_prints_summary_error(self, tmp_path, capsys):
        summary = RunSummary(
            final_status=FinalStatus.ERROR,
            iterations_run=1,
            error_message="runner failed",
        )
        with patch("microbots.auto_memory.cli.run_from_yaml", return_value=summary):
            assert main([str(tmp_path / "task.yaml")]) == 0
        assert "last error: runner failed" in capsys.readouterr().err

    def test_module_entry_point_dispatches_to_main(self):
        with (
            patch("microbots.auto_memory.cli.main", return_value=7),
            pytest.raises(SystemExit, match="7"),
        ):
            runpy.run_module("microbots.auto_memory.__main__", run_name="__main__")

