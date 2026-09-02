"""Unit tests for microbots.auto_memory.task_registry."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.evalTask import EvalTask
from microbots.auto_memory.task_registry import TASK_REGISTRY, create_task, discover_tasks, register_task

MODULE_PATH = "microbots.auto_memory.task_registry"


class _DummyTask(EvalTask):
    def __init__(self, value=None):
        self.value = value

    def setup(self, repo_path):
        pass

    def build_prompt(self):
        return "prompt"

    def check(self, output):
        pass

    def teardown(self, repo_path):
        pass

    def build_feedback(self, outcome, repo_path, model, log_path):
        return "feedback"

    def run(self, repo_path, memory_dir, model):
        return super().run(repo_path, memory_dir, model)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot/restore TASK_REGISTRY so tests don't leak state into each other."""
    original = dict(TASK_REGISTRY)
    yield
    TASK_REGISTRY.clear()
    TASK_REGISTRY.update(original)


@pytest.mark.unit
def test_register_task_adds_class_to_registry():
    register_task("dummy")(_DummyTask)

    assert TASK_REGISTRY["dummy"] is _DummyTask


@pytest.mark.unit
def test_register_task_returns_class_unchanged():
    decorated = register_task("dummy")(_DummyTask)

    assert decorated is _DummyTask


@pytest.mark.unit
def test_create_task_constructs_registered_task_with_kwargs():
    register_task("dummy")(_DummyTask)

    task = create_task("dummy", value=42)

    assert isinstance(task, _DummyTask)
    assert task.value == 42


@pytest.mark.unit
def test_create_task_raises_for_unknown_name():
    with pytest.raises(ValueError, match="Unknown task 'nonexistent'"):
        create_task("nonexistent")


@pytest.mark.unit
def test_discover_tasks_registers_swebenchverified():
    """Non-destructive: confirms discover_tasks() works against the real package."""
    discover_tasks()

    assert "swebenchverified" in TASK_REGISTRY


@pytest.mark.unit
@patch(f"{MODULE_PATH}.importlib.import_module")
@patch(f"{MODULE_PATH}.pkgutil.iter_modules")
def test_discover_tasks_imports_every_module_found_in_package(mock_iter_modules, mock_import_module):
    fake_package = MagicMock()
    fake_package.__path__ = ["/fake/path"]
    mock_import_module.side_effect = (
        lambda name: fake_package if name == "fake.pkg" else MagicMock()
    )
    mock_iter_modules.return_value = [
        SimpleNamespace(name="task_a"),
        SimpleNamespace(name="task_b"),
    ]

    discover_tasks(package_name="fake.pkg")

    mock_iter_modules.assert_called_once_with(["/fake/path"])
    mock_import_module.assert_any_call("fake.pkg")
    mock_import_module.assert_any_call("fake.pkg.task_a")
    mock_import_module.assert_any_call("fake.pkg.task_b")
