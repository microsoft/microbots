"""End-to-end tests for the auto_memory CLI entry point."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microbots.auto_memory import run_from_yaml
from microbots.auto_memory.cli import _load_runner_class
from microbots.auto_memory.data_models import FinalStatus
from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.orchestrator import RunSummary
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


# ---------------------------------------------------------------------------
# Runner construction guards (run_from_yaml)
# ---------------------------------------------------------------------------

_GOOD_RUNNER_SRC = textwrap.dedent("""\
    class R:
        def __init__(self, model):
            self.model = model

        def run(self, ctx, timeout_s):
            return None
""")

_NO_RUN_RUNNER_SRC = textwrap.dedent("""\
    class R:
        def __init__(self, model):
            self.model = model
""")


def _write_custom_runner_yaml(tmp_path: Path, runner_src: str, runner_params: str) -> Path:
    (tmp_path / "custom_runner.py").write_text(runner_src)
    yaml = textwrap.dedent(f"""\
        task_definition: do a thing
        prompt_template: "Goal: {{{{ task }}}}"
        runner: ./custom_runner.py:R
        runner_params:
        {runner_params}
        callbacks:
          - name: always_ok
            command: 'true'
        max_iterations: 1
        timeout_min: 1
        per_iteration_timeout: 30
    """)
    p = tmp_path / "task.yml"
    p.write_text(yaml)
    return p


@pytest.mark.unit
class TestRunnerConstructionGuards:
    def test_bad_runner_params_raises_config_error(self, tmp_path):
        """runner_params that don't match __init__ surface as ConfigError."""
        yaml_path = _write_custom_runner_yaml(
            tmp_path, _GOOD_RUNNER_SRC, runner_params="  unexpected_kwarg: 1"
        )
        with pytest.raises(ConfigError, match="Failed to construct runner"):
            run_from_yaml(str(yaml_path), str(tmp_path / "wd"), model=_MODEL)

    def test_runner_missing_run_raises_config_error(self, tmp_path):
        """A runner without run() fails the AgentRunner protocol check."""
        yaml_path = _write_custom_runner_yaml(
            tmp_path, _NO_RUN_RUNNER_SRC, runner_params="  {}"
        )
        with pytest.raises(ConfigError, match="AgentRunner"):
            run_from_yaml(str(yaml_path), str(tmp_path / "wd"), model=_MODEL)


# ---------------------------------------------------------------------------
# Runner resolution (_load_runner_class)
# ---------------------------------------------------------------------------

_RUNNER_FILE_SRC = textwrap.dedent("""\
    class MyRunner:
        def __init__(self, model, **kwargs):
            self.model = model
            self.kwargs = kwargs

        def run(self, ctx, timeout_s):
            return None
""")


@pytest.mark.unit
class TestLoadRunnerClass:
    def _write_runner(self, tmp_path: Path, name: str = "myrunner.py") -> Path:
        p = tmp_path / name
        p.write_text(_RUNNER_FILE_SRC)
        return p

    # --- file-path form -------------------------------------------------
    def test_file_path_form_loads_class(self, tmp_path):
        self._write_runner(tmp_path)
        cls = _load_runner_class("myrunner.py:MyRunner", base_dir=tmp_path)
        assert cls.__name__ == "MyRunner"
        instance = cls(model=_MODEL, repo_url="x")
        assert instance.model == _MODEL
        assert instance.kwargs == {"repo_url": "x"}

    def test_file_path_form_absolute(self, tmp_path):
        runner = self._write_runner(tmp_path)
        cls = _load_runner_class(f"{runner}:MyRunner", base_dir=Path("/nonexistent"))
        assert cls.__name__ == "MyRunner"

    def test_file_path_missing_class_name(self, tmp_path):
        self._write_runner(tmp_path)
        with pytest.raises(ConfigError, match="expected 'path/to/file.py:ClassName'"):
            _load_runner_class("myrunner.py:", base_dir=tmp_path)

    def test_file_path_missing_file_part(self, tmp_path):
        with pytest.raises(ConfigError, match="expected 'path/to/file.py:ClassName'"):
            _load_runner_class(":MyRunner", base_dir=tmp_path)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(ConfigError, match="Runner file not found"):
            _load_runner_class("does_not_exist.py:MyRunner", base_dir=tmp_path)

    def test_file_import_error(self, tmp_path):
        bad = tmp_path / "bad_runner.py"
        bad.write_text("raise RuntimeError('boom')\n")
        with pytest.raises(ConfigError, match="Failed to import runner file"):
            _load_runner_class("bad_runner.py:MyRunner", base_dir=tmp_path)

    def test_file_spec_none(self, tmp_path):
        self._write_runner(tmp_path)
        with patch(
            "microbots.auto_memory.cli.importlib.util.spec_from_file_location",
            return_value=None,
        ):
            with pytest.raises(ConfigError, match="Cannot load runner module"):
                _load_runner_class("myrunner.py:MyRunner", base_dir=tmp_path)

    def test_file_class_not_found(self, tmp_path):
        self._write_runner(tmp_path)
        with pytest.raises(ConfigError, match="not found"):
            _load_runner_class("myrunner.py:NoSuchRunner", base_dir=tmp_path)

    # --- dotted import path form ---------------------------------------
    def test_dotted_form_loads_class(self, tmp_path):
        cls = _load_runner_class(
            "microbots.auto_memory.runners.writing_bot_runner.WritingBotRunner",
            base_dir=tmp_path,
        )
        assert cls.__name__ == "WritingBotRunner"

    def test_dotted_form_missing_module(self, tmp_path):
        with pytest.raises(ConfigError, match="expected"):
            _load_runner_class("WritingBotRunner", base_dir=tmp_path)

    def test_dotted_form_import_error(self, tmp_path):
        with pytest.raises(ConfigError, match="Cannot import runner module"):
            _load_runner_class("no_such_pkg.module.Klass", base_dir=tmp_path)

    def test_dotted_form_import_time_error(self, tmp_path):
        """A non-ImportError raised while importing the module is wrapped in
        ConfigError instead of escaping as a raw traceback."""
        with patch(
            "microbots.auto_memory.cli.importlib.import_module",
            side_effect=RuntimeError("boom at import"),
        ):
            with pytest.raises(ConfigError, match="Failed to import runner module"):
                _load_runner_class(
                    "microbots.auto_memory.config.TaskConfig", base_dir=tmp_path
                )

    def test_dotted_form_class_not_found(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            _load_runner_class(
                "microbots.auto_memory.config.NoSuchClass", base_dir=tmp_path
            )

    def test_resolved_attribute_not_callable(self, tmp_path):
        """A resolved attribute that is not callable (e.g. a constant) raises a
        clear ConfigError instead of a later cryptic TypeError."""
        const_file = tmp_path / "const_runner.py"
        const_file.write_text("NOT_A_RUNNER = 42\n")
        with pytest.raises(ConfigError, match="not callable"):
            _load_runner_class("const_runner.py:NOT_A_RUNNER", base_dir=tmp_path)
