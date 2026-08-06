"""Tests for training configuration loading and validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.training_source import TrainingSource


def _config(tmp_path: Path, **overrides: object) -> TrainingConfig:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("instructions", encoding="utf-8")
    values = {
        "source": TrainingSource(type="path", path=source),
        "memory_dir": tmp_path / "memory",
        "model": "azure-openai/gpt-4o",
        "agents_md_path": agents,
    }
    values.update(overrides)
    return TrainingConfig(**values)


def test_load_nested_yaml_resolves_paths_and_options(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "instructions.md").write_text("learn", encoding="utf-8")
    config_path = tmp_path / "training.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                "  type: path",
                "  path: source",
                "memory_dir: memory",
                "model: azure-openai/gpt-4o",
                "agents_md_path: instructions.md",
                "iterations: 2",
                "per_iteration_timeout: 10",
                "total_timeout_min: 3",
                "max_bot_steps: 5",
                "reset_memory: true",
            ]
        ),
        encoding="utf-8",
    )

    config = TrainingConfig.load_from_yaml(config_path)

    assert config.source_path == (tmp_path / "source").resolve()
    assert config.memory_dir == (tmp_path / "memory").resolve()
    assert config.agents_md_path == (tmp_path / "instructions.md").resolve()
    assert config.iterations == 2
    assert config.per_iteration_timeout == 10
    assert config.total_timeout_min == 3
    assert config.max_bot_steps == 5
    assert config.reset_memory is True
    assert config.read_agents_md() == "learn"


def test_load_legacy_yaml_uses_defaults_and_absolute_memory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    memory = tmp_path / "memory"
    config_path = tmp_path / "training.yaml"
    config_path.write_text(
        f"source_path: source\nmemory_dir: {memory}\n"
        "model: azure-openai/gpt-4o\n",
        encoding="utf-8",
    )

    config = TrainingConfig.load_from_yaml(config_path)

    assert config.source.path == source.resolve()
    assert config.memory_dir == memory
    assert config.iterations == 3
    assert config.read_agents_md()


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("- item\n", "Expected a YAML mapping"),
        ("model: azure-openai/gpt-4o\nsource_path: .\n", "memory_dir"),
        ("memory_dir: memory\nsource_path: .\n", "model"),
        ("memory_dir: memory\nmodel: azure-openai/gpt-4o\n", "Missing source"),
    ],
)
def test_load_yaml_rejects_invalid_shapes(
    tmp_path: Path, contents: str, message: str
) -> None:
    config_path = tmp_path / "training.yaml"
    config_path.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        TrainingConfig.load_from_yaml(config_path)


def test_load_yaml_reports_missing_and_malformed_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigError, match="not found"):
        TrainingConfig.load_from_yaml(missing)

    config_path = tmp_path / "training.yaml"
    config_path.write_text("ignored", encoding="utf-8")
    with (
        patch("microbots.auto_memory.training.config.yaml.safe_load") as load,
        pytest.raises(ConfigError, match="Failed to parse YAML"),
    ):
        load.side_effect = yaml.YAMLError("bad yaml")
        TrainingConfig.load_from_yaml(config_path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"agents_md_path": Path("missing")}, "agents_md_path"),
        ({"model": ""}, "must not be empty"),
        ({"model": "invalid"}, "must be in the form"),
        ({"model": "unknown/model"}, "unsupported provider"),
        ({"iterations": 0}, "iterations"),
        ({"per_iteration_timeout": 0}, "per_iteration_timeout"),
        ({"total_timeout_min": -1}, "total_timeout_min"),
        ({"max_bot_steps": 0}, "max_bot_steps"),
    ],
)
def test_validate_rejects_invalid_fields(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    config = _config(tmp_path, **overrides)

    with pytest.raises(ConfigError, match=message):
        config.validate()


def test_validate_accepts_valid_config(tmp_path: Path) -> None:
    config = _config(tmp_path)

    config.validate()
