"""Tests for local and git training sources."""

import subprocess
from pathlib import Path
from unittest.mock import call, patch

import pytest

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.training_source import (
    TrainingSource,
    _git_clone,
    _git_fetch_and_checkout,
    _is_existing_git_checkout,
    _run_git,
    looks_like_git_url,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (123, False),
        ("https://example.com/repo", True),
        ("git@example.com:repo", True),
        ("repo.git", True),
        ("local/path", False),
    ],
)
def test_looks_like_git_url(value: object, expected: bool) -> None:
    assert looks_like_git_url(value) is expected  # type: ignore[arg-type]


def test_from_mapping_resolves_all_fields(tmp_path: Path) -> None:
    absolute = tmp_path / "absolute"
    source = TrainingSource.from_mapping(
        {
            "type": "git",
            "path": "checkout",
            "url": 123,
            "ref": 456,
            "cache_dir": absolute,
        },
        base_dir=tmp_path,
    )

    assert source.path == (tmp_path / "checkout").resolve()
    assert source.url == "123"
    assert source.ref == "456"
    assert source.cache_dir == absolute


def test_from_mapping_defaults_optional_fields(tmp_path: Path) -> None:
    source = TrainingSource.from_mapping({"type": "path"}, base_dir=tmp_path)

    assert source.path is None
    assert source.url is None
    assert source.ref is None
    assert source.cache_dir is None


@pytest.mark.parametrize("data", [None, "path"])
def test_from_mapping_requires_mapping(data: object, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="must be a mapping"):
        TrainingSource.from_mapping(data, base_dir=tmp_path)


def test_from_mapping_rejects_invalid_type(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="source.type"):
        TrainingSource.from_mapping({"type": "other"}, base_dir=tmp_path)


def test_legacy_source_detection_and_resolution(tmp_path: Path) -> None:
    remote = TrainingSource.from_legacy_source_path("https://example/repo.git")
    relative = TrainingSource.from_legacy_source_path("source", base_dir=tmp_path)
    absolute = TrainingSource.from_legacy_source_path(tmp_path)

    assert remote == TrainingSource(type="git", url="https://example/repo.git")
    assert relative.path == (tmp_path / "source").resolve()
    assert absolute.path == tmp_path


def test_validate_path_and_git_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    TrainingSource(type="path", path=source).validate()
    TrainingSource(type="git", url="https://example/repo.git").validate()

    invalid = [
        TrainingSource(type="path"),
        TrainingSource(type="path", path=tmp_path / "missing"),
        TrainingSource(type="git"),
        TrainingSource(type="other"),
    ]
    for source_spec in invalid:
        with pytest.raises(ConfigError):
            source_spec.validate()


def test_materialize_local_source_is_noop(tmp_path: Path) -> None:
    source = TrainingSource(type="path", path=tmp_path)

    assert source.materialize(tmp_path / "unused") == tmp_path


def test_materialize_clones_into_selected_destinations(tmp_path: Path) -> None:
    path_dest = tmp_path / "path-dest"
    cache_dest = tmp_path / "cache-dest"
    source = TrainingSource(
        type="git",
        url="https://example/repo.git",
        path=path_dest,
        cache_dir=cache_dest,
    )

    with patch(
        "microbots.auto_memory.training.training_source._git_clone"
    ) as clone:
        assert source.materialize(tmp_path / "default") == cache_dest.resolve()

    clone.assert_called_once_with(
        url="https://example/repo.git", dest=cache_dest.resolve(), ref=None
    )
    assert source.path == cache_dest.resolve()

    default_source = TrainingSource(type="git", url="url")
    with patch(
        "microbots.auto_memory.training.training_source._git_clone"
    ) as clone:
        default_source.materialize(tmp_path / "default")
    assert clone.call_args.kwargs["dest"] == (tmp_path / "default").resolve()


def test_materialize_refreshes_checkout_and_rejects_nonempty_dest(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    source = TrainingSource(type="git", url="url", path=checkout, ref="main")
    with patch(
        "microbots.auto_memory.training.training_source._git_fetch_and_checkout"
    ) as fetch:
        assert source.materialize(tmp_path / "default") == checkout.resolve()
    fetch.assert_called_once_with(checkout.resolve(), url="url", ref="main")

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "file").write_text("data", encoding="utf-8")
    with pytest.raises(ConfigError, match="refusing to clobber"):
        TrainingSource(type="git", url="url", path=nonempty).materialize(
            tmp_path / "default"
        )


def test_metadata_and_checkout_detection(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    source = TrainingSource(
        type="git", path=checkout, url="url", ref="main", cache_dir=tmp_path
    )

    assert _is_existing_git_checkout(checkout)
    assert not _is_existing_git_checkout(tmp_path / "missing")
    assert source.to_meta() == {
        "type": "git",
        "path": str(checkout),
        "url": "url",
        "ref": "main",
        "cache_dir": str(tmp_path),
    }
    assert TrainingSource().to_meta()["path"] is None
    assert TrainingSource().to_meta()["cache_dir"] is None


def test_run_git_success_and_errors(tmp_path: Path) -> None:
    with patch("subprocess.run") as run:
        _run_git(["status"], cwd=tmp_path)
        _run_git(["version"])
    assert run.call_args_list[0].kwargs["cwd"] == str(tmp_path)
    assert run.call_args_list[1].kwargs["cwd"] is None

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(ConfigError, match="executable not found"),
    ):
        _run_git(["status"])

    error = subprocess.CalledProcessError(3, "git", stderr="failure")
    with (
        patch("subprocess.run", side_effect=error),
        pytest.raises(ConfigError, match="failure"),
    ):
        _run_git(["status"])


def test_git_clone_paths(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    with patch(
        "microbots.auto_memory.training.training_source._run_git"
    ) as run:
        _git_clone(url="url", dest=dest, ref=None)
        _git_clone(url="url", dest=dest, ref="main")
    assert run.call_args_list == [
        call(["clone", "url", str(dest)]),
        call(["clone", "--branch", "main", "url", str(dest)]),
    ]


def test_git_clone_retries_commit_and_propagates_without_ref(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    with patch(
        "microbots.auto_memory.training.training_source._run_git",
        side_effect=[ConfigError("branch"), None, None],
    ) as run:
        _git_clone(url="url", dest=dest, ref="abc123")
    assert run.call_args_list[1:] == [
        call(["clone", "url", str(dest)]),
        call(["checkout", "abc123"], cwd=dest),
    ]
    assert not dest.exists()

    with patch(
        "microbots.auto_memory.training.training_source._run_git",
        side_effect=[ConfigError("branch"), None, None],
    ) as run:
        _git_clone(url="url", dest=dest, ref="abc123")
    assert run.call_count == 3

    with (
        patch(
            "microbots.auto_memory.training.training_source._run_git",
            side_effect=ConfigError("clone"),
        ),
        pytest.raises(ConfigError, match="clone"),
    ):
        _git_clone(url="url", dest=dest, ref=None)


def test_git_fetch_checkout_with_and_without_ref(tmp_path: Path) -> None:
    with patch(
        "microbots.auto_memory.training.training_source._run_git"
    ) as run:
        _git_fetch_and_checkout(tmp_path, url="url", ref=None)
    assert run.call_count == 2

    with patch(
        "microbots.auto_memory.training.training_source._run_git",
        side_effect=[None, None, None, ConfigError("detached")],
    ) as run:
        _git_fetch_and_checkout(tmp_path, url="url", ref="main")
    assert run.call_count == 4
