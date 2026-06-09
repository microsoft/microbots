import pytest
from microbots.auto_memory.data_models import (
    CallbackSpec,
    Feedback,
    FinalStatus,
    IterationStatus,
    ReferenceInput,
)


@pytest.mark.unit
class TestReferenceInput:
    def test_defaults(self):
        ri = ReferenceInput(name="spec", value="./spec.md")
        assert ri.is_path is False

    def test_is_path_flag(self):
        ri = ReferenceInput(name="spec", value="./spec.md", is_path=True)
        assert ri.is_path is True

    def test_frozen(self):
        ri = ReferenceInput(name="spec", value="./spec.md")
        with pytest.raises(AttributeError):
            ri.name = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestCallbackSpec:
    def test_defaults(self):
        cb = CallbackSpec(name="tests", command="pytest $CANDIDATE")
        assert cb.timeout_s == 120
        assert cb.expected_return_code == 0

    def test_custom_return_code(self):
        cb = CallbackSpec(name="custom", command="check.sh", expected_return_code=1)
        assert cb.expected_return_code == 1

    def test_frozen(self):
        cb = CallbackSpec(name="tests", command="pytest")
        with pytest.raises(AttributeError):
            cb.name = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestFeedback:
    def test_defaults(self):
        fb = Feedback(iteration_idx=1, summary="Tests failed")
        assert fb.root_causes == []
        assert fb.validator_failures == []
        assert fb.suggested_actions == []

    def test_full(self):
        fb = Feedback(
            iteration_idx=2,
            summary="Two callbacks failed",
            root_causes=["null pointer"],
            validator_failures=["unit_tests", "lint"],
            suggested_actions=["add null check"],
        )
        assert len(fb.validator_failures) == 2

    def test_mutable_lists_are_independent(self):
        fb1 = Feedback(iteration_idx=1, summary="a")
        fb2 = Feedback(iteration_idx=2, summary="b")
        fb1.root_causes.append("x")
        assert fb2.root_causes == []


@pytest.mark.unit
class TestIterationStatus:
    def test_all_values(self):
        assert IterationStatus.PASSED == "passed"
        assert IterationStatus.FAILED == "failed"
        assert IterationStatus.TIMEOUT == "timeout"
        assert IterationStatus.ERROR == "error"
        assert IterationStatus.SKIPPED == "skipped"


@pytest.mark.unit
class TestFinalStatus:
    def test_all_values(self):
        assert FinalStatus.PASSED == "passed"
        assert FinalStatus.LIMIT_REACHED == "limit_reached"
        assert FinalStatus.TIMEOUT == "timeout"
        assert FinalStatus.ERROR == "error"

