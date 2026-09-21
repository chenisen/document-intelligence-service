"""Evidence checking, confidence composition and abstention.

Spec 0003, rules 3, 5, 6 and 7. This is the cheapest and most valuable defence against
hallucination: the excerpt the model quoted is looked for in the recognised text, and a field whose
excerpt is not there falls even with high confidence.
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from core.analysis import ExtractedField
from core.catalog import DocumentTypeSpec
from core.values import Confidence

CRITICAL_THRESHOLD = 0.90
DEFAULT_THRESHOLD = 0.70


class Reason:
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    INVALID_EVIDENCE = "invalid_evidence"
    ABSENT_FROM_DOCUMENT = "absent_from_document"
    VALIDATION_FAILED = "validation_failed"


def fold(text: str) -> str:
    """Case, accent and repeated whitespace do not change whether an excerpt is there."""
    stripped = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(char for char in stripped if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def evidence_is_real(field: ExtractedField, source_text: Mapping[int, str] | str) -> bool:
    if field.evidence is None:
        return False
    text = source_text if isinstance(source_text, str) else source_text.get(field.evidence.page, "")
    excerpt = fold(field.evidence.text)
    return bool(excerpt) and excerpt in fold(text)


def threshold_for(spec: DocumentTypeSpec, field_name: str) -> float:
    return CRITICAL_THRESHOLD if field_name in spec.critical else DEFAULT_THRESHOLD


def compose(model: Confidence, ocr_confidence: float, validation_passed: bool) -> Confidence:
    """One number per field, from the three things that know something about it.

    OCR confidence arrives on a 0 to 100 scale. A failed validation does not zero the field: it
    lowers it enough to cross the threshold and send the case to a person.
    """
    combined = min(model.value, ocr_confidence / 100)
    return Confidence(round(combined * (1.0 if validation_passed else 0.5), 4))


@dataclass(frozen=True)
class Decided:
    """A field after the policy ran: value kept, or dropped with a reason."""

    name: str
    value: object | None
    confidence: Confidence
    abstained: bool
    reason: str | None
    evidence_text: str | None
    evidence_page: int | None


def decide(
    field: ExtractedField,
    spec: DocumentTypeSpec,
    source_text: Mapping[int, str] | str,
    ocr_confidence: float,
    validation_passed: bool = True,
) -> Decided:
    def dropped(reason: str, confidence: Confidence) -> Decided:
        return Decided(field.name, None, confidence, True, reason, None, None)

    if field.value is None:
        # Absent from the document. Never inferred, and this is not a failure.
        return Decided(
            field.name, None, Confidence(1.0), False, Reason.ABSENT_FROM_DOCUMENT, None, None
        )

    if not evidence_is_real(field, source_text):
        return dropped(Reason.INVALID_EVIDENCE, Confidence(0.0))

    confidence = compose(field.confidence, ocr_confidence, validation_passed)
    if confidence.below(threshold_for(spec, field.name)):
        reason = (
            Reason.VALIDATION_FAILED if not validation_passed else Reason.CONFIDENCE_BELOW_THRESHOLD
        )
        return dropped(reason, confidence)

    assert field.evidence is not None
    return Decided(
        field.name,
        field.value,
        confidence,
        False,
        None,
        field.evidence.text,
        field.evidence.page,
    )
