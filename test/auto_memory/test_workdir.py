"""Unit tests for microbots.auto_memory.workdir."""

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/")))

from microbots.auto_memory.workdir import (
    CONFIG_FILENAME,
    eval_dir,
    eval_log_path,
    eval_patch_path,
    eval_repo_dir,
    eval_result_path,
    load_config,
    load_round_memory,
    memory_dir,
    repo_dir,
    require_workdir,
    resolve_workdir,
    round_dir,
    round_log_path,
    round_memory_dir,
    save_round_memory,
    snapshot_seed_memory,
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


@pytest.mark.unit
def test_snapshot_seed_memory_creates_empty_dir_when_no_top_level_memory(tmp_path):
    result = snapshot_seed_memory(tmp_path)

    assert result == tmp_path / "memory_seed"
    assert result.is_dir()
    assert list(result.iterdir()) == []


@pytest.mark.unit
def test_snapshot_seed_memory_copies_current_top_level_memory(tmp_path):
    top_memory = memory_dir(tmp_path)
    top_memory.mkdir(parents=True)
    (top_memory / "notes.md").write_text("original seed")

    result = snapshot_seed_memory(tmp_path)

    assert (result / "notes.md").read_text() == "original seed"


@pytest.mark.unit
def test_snapshot_seed_memory_is_a_noop_once_a_snapshot_exists(tmp_path):
    top_memory = memory_dir(tmp_path)
    top_memory.mkdir(parents=True)
    (top_memory / "notes.md").write_text("original seed")
    snapshot_seed_memory(tmp_path)

    # Mutate top-level memory as later rounds/instances would.
    (top_memory / "notes.md").write_text("overwritten by later training")

    result = snapshot_seed_memory(tmp_path)

    assert (result / "notes.md").read_text() == "original seed"


@pytest.mark.unit
def test_resolve_workdir_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert resolve_workdir() == tmp_path / "workdir"


@pytest.mark.unit
def test_resolve_workdir_uses_given_base(tmp_path):
    assert resolve_workdir(tmp_path) == tmp_path / "workdir"


@pytest.mark.unit
def test_require_workdir_raises_when_missing(tmp_path):
    missing = tmp_path / "nope"

    with pytest.raises(FileNotFoundError):
        require_workdir(missing)


@pytest.mark.unit
def test_require_workdir_passes_when_present(tmp_path):
    require_workdir(tmp_path)


@pytest.mark.unit
def test_repo_dir_returns_workdir_repo(tmp_path):
    assert repo_dir(tmp_path) == tmp_path / "repo"


@pytest.mark.unit
def test_eval_repo_dir_returns_workdir_eval_repo(tmp_path):
    assert eval_repo_dir(tmp_path) == tmp_path / "eval_repo"


@pytest.mark.unit
def test_round_dir_creates_directory_when_requested(tmp_path):
    path = round_dir(tmp_path, 1, create=True)

    assert path == tmp_path / "rounds" / "round_1"
    assert path.is_dir()


@pytest.mark.unit
def test_round_dir_does_not_create_directory_by_default(tmp_path):
    path = round_dir(tmp_path, 1)

    assert path == tmp_path / "rounds" / "round_1"
    assert not path.exists()


@pytest.mark.unit
def test_round_dir_uses_per_instance_dir_when_instance_id_given(tmp_path):
    path = round_dir(tmp_path, 1, instance_id="task-1")

    assert path == tmp_path / "rounds_task-1" / "round_1"


@pytest.mark.unit
def test_round_log_path_returns_round_log(tmp_path):
    assert round_log_path(tmp_path, 2) == round_dir(tmp_path, 2) / "round.log"


@pytest.mark.unit
def test_round_log_path_with_instance_id(tmp_path):
    assert round_log_path(tmp_path, 2, instance_id="task-1") == round_dir(
        tmp_path, 2, instance_id="task-1"
    ) / "round.log"


@pytest.mark.unit
def test_eval_dir_creates_directory_when_requested(tmp_path):
    path = eval_dir(tmp_path, 1, "task-1", create=True)

    assert path == tmp_path / "rounds_task-1" / "round_1" / "eval"
    assert path.is_dir()


@pytest.mark.unit
def test_eval_dir_does_not_create_directory_by_default(tmp_path):
    path = eval_dir(tmp_path, 1, "task-1")

    assert path == tmp_path / "rounds_task-1" / "round_1" / "eval"
    assert not path.exists()


@pytest.mark.unit
def test_eval_result_path_returns_result_json(tmp_path):
    assert eval_result_path(tmp_path, 1, "task-1") == eval_dir(tmp_path, 1, "task-1") / "result.json"


@pytest.mark.unit
def test_eval_log_path_returns_eval_log(tmp_path):
    assert eval_log_path(tmp_path, 1, "task-1") == eval_dir(tmp_path, 1, "task-1") / "eval.log"


@pytest.mark.unit
def test_eval_patch_path_returns_repo_patch(tmp_path):
    assert eval_patch_path(tmp_path, 1, "task-1") == eval_dir(tmp_path, 1, "task-1") / "repo.patch"
