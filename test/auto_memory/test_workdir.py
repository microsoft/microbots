"""Unit tests for microbots.auto_memory.workdir."""

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.workdir import (
    CONFIG_FILENAME,
    load_config,
    load_round_memory,
    memory_dir,
    round_memory_dir,
    save_round_memory,
)


@pytest.mark.unit
def test_load_config_returns_empty_dict_when_file_missing(tmp_path):
    assert load_config(tmp_path) == {}


@pytest.mark.unit
def test_load_config_returns_empty_dict_when_file_empty(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("")

    assert load_config(tmp_path) == {}


@pytest.mark.unit
def test_load_config_parses_yaml_contents(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("repo: https://example.com/repo.git\ntask: swebenchverified\n")

    assert load_config(tmp_path) == {
        "repo": "https://example.com/repo.git",
        "task": "swebenchverified",
    }


@pytest.mark.unit
def test_load_round_memory_creates_empty_dir_when_no_top_level_memory(tmp_path):
    result = load_round_memory(tmp_path, 1)

    assert result == round_memory_dir(tmp_path, 1)
    assert result.is_dir()
    assert list(result.iterdir()) == []


@pytest.mark.unit
def test_load_round_memory_copies_top_level_memory_into_round(tmp_path):
    top_memory = memory_dir(tmp_path)
    top_memory.mkdir(parents=True)
    (top_memory / "notes.md").write_text("prior findings")

    result = load_round_memory(tmp_path, 2)

    assert (result / "notes.md").read_text() == "prior findings"


@pytest.mark.unit
def test_save_round_memory_creates_empty_dir_when_no_round_memory(tmp_path):
    result = save_round_memory(tmp_path, 1)

    assert result == memory_dir(tmp_path)
    assert result.is_dir()
    assert list(result.iterdir()) == []


@pytest.mark.unit
def test_save_round_memory_copies_round_memory_to_top_level(tmp_path):
    round_memory = round_memory_dir(tmp_path, 3)
    round_memory.mkdir(parents=True)
    (round_memory / "learned.md").write_text("new insight")

    result = save_round_memory(tmp_path, 3)

    assert (result / "learned.md").read_text() == "new insight"


@pytest.mark.unit
def test_save_round_memory_overwrites_stale_top_level_files(tmp_path):
    top_memory = memory_dir(tmp_path)
    top_memory.mkdir(parents=True)
    (top_memory / "notes.md").write_text("old")

    round_memory = round_memory_dir(tmp_path, 1)
    round_memory.mkdir(parents=True)
    (round_memory / "notes.md").write_text("new")

    save_round_memory(tmp_path, 1)

    assert (top_memory / "notes.md").read_text() == "new"
