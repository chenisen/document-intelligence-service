import pytest

from core.analysis import ExtractedField
from core.catalog import DocumentTypeSpec
from core.policy import Reason, compose_field_confidence, decide_field
from core.values import Confidence, Evidence

CERTIFICATE = DocumentTypeSpec(
    fields=("leave_period", "patient_name", "crm", "doctor_name"),
    critical=frozenset({"leave_period"}),
)
ASSESSMENT = DocumentTypeSpec(
    fields=("outcome", "granted_period", "cid"), critical=frozenset({"outcome"})
)


@pytest.mark.parametrize("page", [1, 3])
def test_evidence_on_another_or_missing_page_drops_the_field(page):
    field = ExtractedField("crm", "123456/SP", Confidence(1), Evidence("123456/SP", page))

    result = decide_field(field, CERTIFICATE, {1: "Médico", 2: "123456/SP"}, 100)

    assert result.value is None
    assert result.abstained
    assert result.reason == Reason.INVALID_EVIDENCE


def test_evidence_is_checked_on_its_page_ignoring_case_accents_and_whitespace():
    field = ExtractedField(
        "doctor_name", "José Silva", Confidence(0.99), Evidence("Doutor José Silva", 2)
    )

    result = decide_field(field, CERTIFICATE, {1: "Atestado", 2: "DOUTOR JOSE\n  SILVA"}, 98)

    assert result.value == "José Silva"
    assert result.confidence.value == 0.98
    assert result.evidence_text == "Doutor José Silva"
    assert result.evidence_page == 2
    assert not result.abstained


@pytest.mark.parametrize("evidence", [None, Evidence("CRM inventado", 1), Evidence("\u0301", 1)])
def test_missing_fabricated_or_empty_folded_evidence_drops_the_field(evidence):
    field = ExtractedField("crm", "123456/SP", Confidence(1), evidence)

    result = decide_field(field, CERTIFICATE, "Nome do médico", 100)

    assert result.value is None
    assert result.confidence.value == 0
    assert result.reason == Reason.INVALID_EVIDENCE


@pytest.mark.parametrize(
    ("spec", "name", "confidence", "abstained"),
    [
        (CERTIFICATE, "leave_period", 0.8999, True),
        (CERTIFICATE, "leave_period", 0.90, False),
        (ASSESSMENT, "outcome", 0.8999, True),
        (ASSESSMENT, "outcome", 0.90, False),
        (CERTIFICATE, "patient_name", 0.6999, True),
        (CERTIFICATE, "patient_name", 0.70, False),
    ],
)
def test_critical_and_regular_fields_use_their_threshold(spec, name, confidence, abstained):
    field = ExtractedField(name, "value", Confidence(confidence), Evidence("value", 1))

    result = decide_field(field, spec, "value", 100)

    assert result.abstained is abstained
    assert result.value == (None if abstained else "value")
    assert result.reason == (Reason.CONFIDENCE_BELOW_THRESHOLD if abstained else None)


@pytest.mark.parametrize(
    ("model", "ocr", "valid", "expected"),
    [(0.99, 80, True, 0.8), (0.75, 99, True, 0.75), (0.99, 80, False, 0.4)],
)
def test_confidence_combines_ocr_model_and_validation(model, ocr, valid, expected):
    assert compose_field_confidence(Confidence(model), ocr, valid).value == expected


def test_failed_validation_abstains_with_its_own_reason():
    field = ExtractedField("crm", "123/SP", Confidence(1), Evidence("123/SP", 1))

    result = decide_field(field, CERTIFICATE, "123/SP", 100, False)

    assert result.value is None
    assert result.abstained
    assert result.reason == Reason.VALIDATION_FAILED


@pytest.mark.parametrize("name", ["cid", "granted_period"])
def test_absent_fields_stay_null_without_guessing_or_abstention(name):
    field = ExtractedField(name, None, Confidence(0.1), None)

    result = decide_field(field, ASSESSMENT, "texto", 10)

    assert result.value is None
    assert not result.abstained
    assert result.reason == Reason.ABSENT_FROM_DOCUMENT
    assert result.evidence_text is None
