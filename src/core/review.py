"""When a person has to look at the case.

Spec 0004, rule 8. The service decides that a human is needed. The review happens in the consumer,
which owns the screen and flow. The service never decides anything about a person by itself.

Reasons are codes, not sentences: the consumer routes on them without parsing text.
"""

from dataclasses import dataclass

from core.catalog import DocumentTypeSpec
from core.policy import Decided, Reason
from core.validation import Validation

CLASSIFICATION_THRESHOLD = 0.80


@dataclass(frozen=True)
class Review:
    required: bool
    reasons: tuple[str, ...]


def decide_review(
    spec: DocumentTypeSpec,
    fields: list[Decided],
    validations: list[Validation],
    classification_confidence: float,
    marginal_quality: bool = False,
    guardrail_triggered: bool = False,
) -> Review:
    reasons: list[str] = []

    for field in fields:
        if field.reason == Reason.CONFIDENCE_BELOW_THRESHOLD:
            reasons.append(f"confidence_below_threshold:{field.name}")
        elif field.reason == Reason.INVALID_EVIDENCE:
            reasons.append(f"invalid_evidence:{field.name}")

    present = {field.name for field in fields if field.value is not None}
    reasons += [f"critical_field_missing:{name}" for name in sorted(spec.critical - present)]

    reasons += [f"validation_failed:{rule.rule}" for rule in validations if not rule.passed]

    if classification_confidence < CLASSIFICATION_THRESHOLD:
        reasons.append("uncertain_classification")
    if guardrail_triggered:
        reasons.append("guardrail_triggered")
    if marginal_quality:
        reasons.append("marginal_quality")

    ordered = tuple(dict.fromkeys(reasons))
    return Review(required=bool(ordered), reasons=ordered)
