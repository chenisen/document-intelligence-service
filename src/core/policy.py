import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from core.analysis import ExtractedField
from core.catalog import DocumentTypeSpec
from core.values import Confidence

CRITICAL_THRESHOLD = 0.90
DEFAULT_THRESHOLD = 0.70
FAILED_VALIDATION_CONFIDENCE_FACTOR = 0.5


class Reason:
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    INVALID_EVIDENCE = "invalid_evidence"
    ABSENT_FROM_DOCUMENT = "absent_from_document"
    VALIDATION_FAILED = "validation_failed"


def normalize_evidence_text(text: str) -> str:
    decomposed_text = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(char for char in decomposed_text if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def evidence_exists_on_page(field: ExtractedField, source_text: Mapping[int, str] | str) -> bool:
    if field.evidence is None:
        return False
    text = source_text if isinstance(source_text, str) else source_text.get(field.evidence.page, "")
    excerpt = normalize_evidence_text(field.evidence.text)
    return bool(excerpt) and excerpt in normalize_evidence_text(text)


def field_confidence_threshold(spec: DocumentTypeSpec, field_name: str) -> float:
    return CRITICAL_THRESHOLD if field_name in spec.critical else DEFAULT_THRESHOLD


def compose_field_confidence(
    model_confidence: Confidence, ocr_confidence: float, validation_passed: bool
) -> Confidence:
    reading_confidence = min(model_confidence.value, ocr_confidence / 100)
    validation_factor = 1.0 if validation_passed else FAILED_VALIDATION_CONFIDENCE_FACTOR
    return Confidence(round(reading_confidence * validation_factor, 4))


@dataclass(frozen=True)
class FieldDecision:
    name: str
    value: object | None
    confidence: Confidence
    abstained: bool
    reason: str | None
    evidence_text: str | None
    evidence_page: int | None


def decide_field(
    field: ExtractedField,
    spec: DocumentTypeSpec,
    source_text: Mapping[int, str] | str,
    ocr_confidence: float,
    validation_passed: bool = True,
) -> FieldDecision:
    def abstain_from_field(reason: str, confidence: Confidence) -> FieldDecision:
        return FieldDecision(field.name, None, confidence, True, reason, None, None)

    if field.value is None:
        return FieldDecision(
            field.name, None, Confidence(1.0), False, Reason.ABSENT_FROM_DOCUMENT, None, None
        )

    if not evidence_exists_on_page(field, source_text):
        return abstain_from_field(Reason.INVALID_EVIDENCE, Confidence(0.0))

    confidence = compose_field_confidence(field.confidence, ocr_confidence, validation_passed)
    if confidence.below(field_confidence_threshold(spec, field.name)):
        reason = (
            Reason.VALIDATION_FAILED if not validation_passed else Reason.CONFIDENCE_BELOW_THRESHOLD
        )
        return abstain_from_field(reason, confidence)

    assert field.evidence is not None
    return FieldDecision(
        field.name,
        field.value,
        confidence,
        False,
        None,
        field.evidence.text,
        field.evidence.page,
    )
