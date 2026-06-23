import pytest
from unittest.mock import patch
from pathlib import Path

from microbots.auto_memory.memory import MemoryStore
from microbots.auto_memory.data_models import Feedback
from microbots.auto_memory.errors import MemoryStoreError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feedback(idx: int = 0, summary: str = "Tests failed") -> Feedback:
    return Feedback(iteration_idx=idx, summary=summary)


# ---------------------------------------------------------------------------
# Mount behaviour
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryStoreMount:
    def test_mount_creates_memory_directory(self, tmp_path):
        store = MemoryStore()
        store.mount(tmp_path / "run")
        assert (tmp_path / "run" / "memory").is_dir()

    def test_mount_non_resume_creates_empty_file(self, tmp_path):
        run_dir = tmp_path / "run"
        store = MemoryStore()
        store.mount(run_dir, resume=False)
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        assert feedback_file.exists()
        assert feedback_file.read_text(encoding="utf-8") == ""

    def test_mount_non_resume_wipes_existing_feedback(self, tmp_path):
        run_dir = tmp_path / "run"
        store = MemoryStore()
        store.mount(run_dir)
        store.append_feedback(_make_feedback(0, "Old failure"))

        store2 = MemoryStore()
        store2.mount(run_dir, resume=False)
        assert store2.read_all() == []

    def test_mount_resume_preserves_existing_feedback(self, tmp_path):
        run_dir = tmp_path / "run"
        store = MemoryStore()
        store.mount(run_dir)
        store.append_feedback(_make_feedback(0, "First failure"))

        store2 = MemoryStore()
        store2.mount(run_dir, resume=True)
        entries = store2.read_all()
        assert len(entries) == 1
        assert entries[0].summary == "First failure"

    def test_mount_idempotent_called_twice(self, tmp_path):
        run_dir = tmp_path / "run"
        store = MemoryStore()
        store.mount(run_dir)
        store.append_feedback(_make_feedback(0, "entry"))
        store.mount(run_dir, resume=False)  # second mount wipes
        assert store.read_all() == []


# ---------------------------------------------------------------------------
# Unmounted guard
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryStoreUnmountedGuard:
    def test_unmounted_raises_on_append(self):
        store = MemoryStore()
        with pytest.raises(MemoryStoreError, match="not been mounted"):
            store.append_feedback(_make_feedback())

    def test_unmounted_raises_on_read_all(self):
        store = MemoryStore()
        with pytest.raises(MemoryStoreError, match="not been mounted"):
            store.read_all()

    def test_unmounted_raises_on_clear(self):
        store = MemoryStore()
        with pytest.raises(MemoryStoreError, match="not been mounted"):
            store.clear()

    def test_unmounted_raises_on_persist(self):
        store = MemoryStore()
        with pytest.raises(MemoryStoreError, match="not been mounted"):
            store.persist()


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryStoreReadWrite:
    @pytest.fixture
    def store(self, tmp_path) -> MemoryStore:
        s = MemoryStore()
        s.mount(tmp_path / "run")
        return s

    def test_read_all_empty_before_any_append(self, store):
        assert store.read_all() == []

    def test_append_and_read_single(self, store):
        fb = Feedback(iteration_idx=0, summary="Tests failed")
        store.append_feedback(fb)
        entries = store.read_all()
        assert len(entries) == 1
        assert entries[0].iteration_idx == 0
        assert entries[0].summary == "Tests failed"

    def test_append_multiple_preserves_order(self, store):
        for i in range(3):
            store.append_feedback(_make_feedback(i, f"Failure {i}"))
        entries = store.read_all()
        assert [e.iteration_idx for e in entries] == [0, 1, 2]

    def test_append_full_feedback_round_trips(self, store):
        fb = Feedback(
            iteration_idx=1,
            summary="Two callbacks failed",
            root_causes=["null pointer"],
            validator_failures=["unit_tests", "lint"],
            suggested_actions=["add null check"],
        )
        store.append_feedback(fb)
        entries = store.read_all()
        assert entries[0].root_causes == ["null pointer"]
        assert entries[0].validator_failures == ["unit_tests", "lint"]
        assert entries[0].suggested_actions == ["add null check"]

    def test_clear_removes_all_entries(self, store):
        store.append_feedback(_make_feedback())
        store.clear()
        assert store.read_all() == []

    def test_clear_then_append_works(self, store):
        store.append_feedback(_make_feedback(0, "old"))
        store.clear()
        store.append_feedback(_make_feedback(1, "new"))
        entries = store.read_all()
        assert len(entries) == 1
        assert entries[0].summary == "new"

    def test_persist_is_safe_to_call_and_preserves_data(self, store):
        store.append_feedback(_make_feedback())
        store.persist()  # must not raise or lose data
        assert len(store.read_all()) == 1

    def test_read_all_no_file_returns_empty(self, tmp_path):
        """read_all() returns [] when the feedback file has been deleted."""
        # Mount normally (clear() creates the file), then delete it to
        # simulate the absent-file path without touching private attributes.
        run_dir = tmp_path / "run2"
        store = MemoryStore()
        store.mount(run_dir)
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        feedback_file.unlink()  # remove the empty file clear() created
        assert store.read_all() == []

    def test_read_all_skips_corrupt_jsonl(self, tmp_path, caplog):
        """read_all() skips and warns on a line that is not valid JSON."""
        import logging
        run_dir = tmp_path / "run3"
        store = MemoryStore()
        store.mount(run_dir)
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        feedback_file.write_text("{not valid json}\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            entries = store.read_all()
        assert entries == []
        assert any("corrupt" in r.message.lower() for r in caplog.records)

    def test_read_all_skips_non_object_json(self, tmp_path, caplog):
        """read_all() skips and warns on a valid-JSON line that is not an object."""
        import logging
        run_dir = tmp_path / "run4"
        store = MemoryStore()
        store.mount(run_dir)
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        feedback_file.write_text("[1, 2, 3]\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            entries = store.read_all()
        assert entries == []
        assert any("non-object" in r.message.lower() for r in caplog.records)

    def test_read_all_skips_missing_required_fields(self, tmp_path, caplog):
        """read_all() skips and warns when required Feedback fields are absent."""
        import logging
        run_dir = tmp_path / "run5"
        store = MemoryStore()
        store.mount(run_dir)
        feedback_file = run_dir / "memory" / "feedback.jsonl"
        # Missing both iteration_idx and summary (required, no default).
        feedback_file.write_text('{"root_causes": []}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            entries = store.read_all()
        assert entries == []
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_read_all_ignores_unknown_fields(self, tmp_path):
        """read_all() silently drops fields not present in Feedback."""
        run_dir = tmp_path / "run3"
        run_dir.mkdir()
        store = MemoryStore()
        store.mount(run_dir, resume=True)
        # Write a line that has an extra future-schema field.
        feedback_path = run_dir / "memory" / "feedback.jsonl"
        feedback_path.write_text(
            '{"iteration_idx": 0, "summary": "ok", "root_causes": [], '
            '"validator_failures": [], "suggested_actions": [], "future_field": "x"}\n',
            encoding="utf-8",
        )
        entries = store.read_all()
        assert len(entries) == 1
        assert entries[0].summary == "ok"


# ---------------------------------------------------------------------------
# OSError paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMemoryStoreOSErrors:
    def test_mount_mkdir_failure_raises(self, tmp_path):
        store = MemoryStore()
        with patch.object(Path, "mkdir", side_effect=OSError("disk full")):
            with pytest.raises(MemoryStoreError, match="Cannot create memory directory"):
                store.mount(tmp_path / "run")

    def test_append_feedback_open_failure_raises(self, tmp_path):
        store = MemoryStore()
        store.mount(tmp_path / "run")
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            with pytest.raises(MemoryStoreError, match="Failed to write feedback"):
                store.append_feedback(_make_feedback())

    def test_read_all_open_failure_raises(self, tmp_path):
        store = MemoryStore()
        store.mount(tmp_path / "run")
        store.append_feedback(_make_feedback())  # ensure file exists
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            with pytest.raises(MemoryStoreError, match="Failed to read feedback"):
                store.read_all()

    def test_clear_write_text_failure_raises(self, tmp_path):
        store = MemoryStore()
        store.mount(tmp_path / "run")  # succeeds — creates empty file
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            with pytest.raises(MemoryStoreError, match="Failed to clear feedback file"):
                store.clear()
