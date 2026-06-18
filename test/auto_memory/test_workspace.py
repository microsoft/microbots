import json
import pytest
from pathlib import Path

from microbots.auto_memory.workspace import WorkspaceManager
from microbots.auto_memory.data_models import Feedback
from microbots.auto_memory.errors import ConfigError


# ---------------------------------------------------------------------------
# prepare() — fresh run
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWorkspaceManagerPrepare:
    def test_prepare_creates_run_dir(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "run")
        wm.prepare()
        assert (tmp_path / "run").is_dir()

    def test_prepare_creates_memory_dir(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "run")
        wm.prepare()
        assert (tmp_path / "run" / "memory").is_dir()

    def test_prepare_creates_iterations_dir(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "run")
        wm.prepare()
        assert (tmp_path / "run" / "iterations").is_dir()

    def test_prepare_creates_run_meta(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "run")
        wm.prepare()
        meta_file = tmp_path / "run" / "run_meta.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert "created_at" in meta
        assert "run_dir" in meta

    def test_prepare_non_resume_wipes_existing_content(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "leftover.txt").write_text("old")
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare(resume=False)
        assert not (run_dir / "leftover.txt").exists()

    def test_prepare_on_new_dir_with_resume_false_succeeds(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "brand_new")
        wm.prepare(resume=False)
        assert (tmp_path / "brand_new").is_dir()

    def test_prepare_iteration_count_starts_at_zero(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "run")
        wm.prepare()
        assert wm.iteration_count == 0


# ---------------------------------------------------------------------------
# prepare() — resume=True
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWorkspaceManagerResume:
    def test_prepare_resume_true_raises_if_dir_missing(self, tmp_path):
        wm = WorkspaceManager(run_dir=tmp_path / "nonexistent")
        with pytest.raises(ConfigError, match="does not exist"):
            wm.prepare(resume=True)

    def test_prepare_resume_preserves_existing_files(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        sentinel = run_dir / "keep_me.txt"
        sentinel.write_text("preserved")

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert sentinel.read_text() == "preserved"

    def test_prepare_resume_detects_prior_iteration_count(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(0)
        wm.prepare_iteration(1)

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 2
        # Existing iteration directories must still be present after resume.
        assert (run_dir / "iterations" / "iter_00").is_dir()
        assert (run_dir / "iterations" / "iter_01").is_dir()

    def test_prepare_resume_mounts_memory_without_clearing(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.memory.append_feedback(Feedback(iteration_idx=0, summary="prior failure"))

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        entries = wm2.memory.read_all()
        assert len(entries) == 1
        assert entries[0].summary == "prior failure"

    def test_prepare_resume_no_iterations_returns_zero(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 0

    def test_prepare_resume_gap_in_indices(self, tmp_path):
        """Only iter_05 exists; iteration_count must be 6, not 1."""
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(5)  # creates iter_05, skips 0-4

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 6

    def test_prepare_resume_large_index(self, tmp_path):
        """iter_100 exists; iteration_count must be 101, not 1."""
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(100)

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 101


# ---------------------------------------------------------------------------
# prepare_iteration() / iteration_dir()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWorkspaceManagerIterations:
    @pytest.fixture
    def wm(self, tmp_path) -> WorkspaceManager:
        m = WorkspaceManager(run_dir=tmp_path / "run")
        m.prepare()
        return m

    def test_prepare_iteration_creates_candidate_dir(self, wm):
        idir = wm.prepare_iteration(0)
        assert (idir / "candidate").is_dir()

    def test_prepare_iteration_creates_logs_dir(self, wm):
        idir = wm.prepare_iteration(0)
        assert (idir / "logs").is_dir()

    def test_iteration_dir_naming_zero_padded(self, wm):
        assert wm.iteration_dir(0).name == "iter_00"
        assert wm.iteration_dir(5).name == "iter_05"
        assert wm.iteration_dir(10).name == "iter_10"

    def test_prepare_iteration_returns_correct_path(self, wm):
        idir = wm.prepare_iteration(3)
        assert idir == wm.iteration_dir(3)

    def test_iteration_count_increments_on_prepare(self, wm):
        assert wm.iteration_count == 0
        wm.prepare_iteration(0)
        assert wm.iteration_count == 1
        wm.prepare_iteration(1)
        assert wm.iteration_count == 2

    def test_iteration_dir_not_created_by_iteration_dir(self, wm):
        path = wm.iteration_dir(99)
        assert not path.exists()

    def test_prepare_iteration_negative_index_raises(self, wm):
        with pytest.raises(ConfigError, match=">= 0"):
            wm.prepare_iteration(-1)

    def test_prepare_iteration_non_sequential_index(self, wm):
        """Calling prepare_iteration(5) as the first call is allowed
        and iteration_count reflects the highest index + 1."""
        idir = wm.prepare_iteration(5)
        assert idir.name == "iter_05"
        assert (idir / "candidate").is_dir()
        assert wm.iteration_count == 6


@pytest.mark.unit
class TestWorkspaceManagerReset:
    def test_reset_wipes_iteration_content(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(0)
        output = wm.iteration_dir(0) / "candidate" / "output.py"
        output.write_text("agent code")

        wm.reset()

        assert run_dir.is_dir()
        assert not (run_dir / "iterations" / "iter_00").exists()

    def test_reset_clears_memory(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.memory.append_feedback(Feedback(iteration_idx=0, summary="old"))

        wm.reset()

        assert wm.memory.read_all() == []

    def test_reset_resets_iteration_count(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(0)
        wm.prepare_iteration(1)

        wm.reset()

        assert wm.iteration_count == 0


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWorkspaceManagerCleanup:
    def test_cleanup_removes_pycache(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        pycache = run_dir / "iterations" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "module.cpython-312.pyc").write_text("")

        wm.cleanup()

        assert not pycache.exists()

    def test_cleanup_removes_pyc_files(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        pyc = run_dir / "candidate" / "module.pyc"
        pyc.parent.mkdir(parents=True, exist_ok=True)
        pyc.write_text("")

        wm.cleanup()

        assert not pyc.exists()

    def test_cleanup_preserves_result_files(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        result = run_dir / "result.txt"
        result.write_text("final output")

        wm.cleanup()

        assert result.read_text() == "final output"

    def test_cleanup_is_safe_on_empty_run_dir(self, tmp_path):
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.cleanup()  # must not raise


# ---------------------------------------------------------------------------
# _safe_rmtree()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSafeRmtree:
    def test_normal_deep_path_is_deleted(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        target.mkdir(parents=True)
        (target / "file.txt").write_text("x")
        WorkspaceManager._safe_rmtree(target)
        assert not target.exists()

    def test_root_path_raises(self):
        with pytest.raises(ConfigError, match="Refusing"):
            WorkspaceManager._safe_rmtree(Path("/"))

    def test_near_root_path_raises(self, tmp_path):
        # Construct a path that resolves to only 2 parts, e.g. /tmp itself.
        # tmp_path is something like /tmp/pytest-xxx/test_0; its parent chain
        # includes /tmp which has parts ('/', 'tmp') — length 2.
        near_root = Path("/tmp")
        with pytest.raises(ConfigError, match="Refusing"):
            WorkspaceManager._safe_rmtree(near_root)


# ---------------------------------------------------------------------------
# _detect_iteration_count() edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDetectIterationCount:
    def test_ignores_dirs_without_iter_prefix(self, tmp_path):
        """Directories not starting with 'iter_' are skipped (continue branch)."""
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(0)
        (wm._iterations_dir / "temp").mkdir()        # no iter_ prefix

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 1  # only iter_00 counts

    def test_ignores_dirs_with_non_digit_suffix(self, tmp_path):
        """Directories like 'iter_foo' (non-digit suffix) are skipped."""
        run_dir = tmp_path / "run"
        wm = WorkspaceManager(run_dir=run_dir)
        wm.prepare()
        wm.prepare_iteration(2)
        (wm._iterations_dir / "iter_foo").mkdir()    # iter_ prefix, non-digit suffix

        wm2 = WorkspaceManager(run_dir=run_dir)
        wm2.prepare(resume=True)
        assert wm2.iteration_count == 3  # only iter_02 counts → max_idx=2, +1=3


# ---------------------------------------------------------------------------
# _write_meta() error path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWriteMeta:
    def test_write_meta_oserror_logs_warning_not_raises(self, tmp_path):
        """_write_meta() swallows OSError and logs a warning instead of raising."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Block the meta path by creating a directory there so write_text raises.
        (run_dir / "run_meta.json").mkdir()
        wm = WorkspaceManager(run_dir=run_dir)
        wm._write_meta()  # must not raise
