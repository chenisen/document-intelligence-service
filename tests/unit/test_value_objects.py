import pytest

from core.document import Page
from core.values import Confidence, Evidence


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_confidence_accepts_the_whole_range(value: float) -> None:
    assert Confidence(value).value == value


@pytest.mark.parametrize("value", [-0.01, 1.01, 7.2])
def test_confidence_rejects_anything_outside_zero_to_one(value: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Confidence(value)


def test_confidence_compares_against_a_threshold() -> None:
    assert Confidence(0.4).below(0.7)
    assert not Confidence(0.9).below(0.7)


def test_evidence_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        Evidence(text="   ", page=1)


@pytest.mark.parametrize("page", [0, -1])
def test_evidence_rejects_page_numbers_below_one(page: int) -> None:
    with pytest.raises(ValueError, match="starts at 1"):
        Evidence(text="CRM/SP 999001", page=page)


def test_page_rejects_page_numbers_below_one() -> None:
    with pytest.raises(ValueError, match="starts at 1"):
        Page(number=0, image=b"", width=100, height=100)


def test_value_objects_are_frozen() -> None:
    confidence = Confidence(0.9)
    with pytest.raises(AttributeError):
        confidence.value = 0.1  # type: ignore[misc]
