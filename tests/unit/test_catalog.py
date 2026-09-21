"""RF-05 and RF-11: the shipped catalogue, and what configuration buys.

The PRD claims a new document type enters by configuration. This file is where that claim is either
true or a slogan: it adds a third type to a catalogue file and checks that the pipeline reads it,
validates it and applies its thresholds without a single line of code changing.
"""

import json
from datetime import date

import pytest

from adapters.catalog import CATALOG, load_catalog
from core.catalog import Catalog
from core.document import DocumentType
from core.policy import CRITICAL_THRESHOLD, DEFAULT_THRESHOLD, threshold_for
from core.validation import validate

TODAY = date(2026, 9, 18)


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load_catalog()


def test_the_shipped_catalogue_covers_the_two_mvp_types(catalog: Catalog) -> None:
    assert set(catalog.types) == {
        DocumentType.MEDICAL_CERTIFICATE,
        DocumentType.MEDICAL_ASSESSMENT_RESULT,
    }


@pytest.mark.parametrize(
    ("document_type", "critical"),
    [
        (DocumentType.MEDICAL_CERTIFICATE, {"leave_period", "crm"}),
        (DocumentType.MEDICAL_ASSESSMENT_RESULT, {"outcome"}),
    ],
)
def test_each_type_declares_the_fields_that_must_not_be_guessed(
    catalog: Catalog, document_type: DocumentType, critical: set[str]
) -> None:
    spec = catalog.types[document_type]

    assert spec.critical == critical
    assert critical <= set(spec.fields)
    for name in critical:
        assert threshold_for(spec, name) == CRITICAL_THRESHOLD
    assert threshold_for(spec, "doctor_name") == DEFAULT_THRESHOLD


def test_the_reference_table_is_configuration_and_carries_its_version(
    catalog: Catalog,
) -> None:
    """The CID table is content. It has a version because provenance reports which one answered."""
    assert catalog.reference_tables_version
    assert catalog.cid_codes

    rules = validate(
        catalog.types[DocumentType.MEDICAL_CERTIFICATE], catalog, {"cid": "NOT-A-CODE"}, TODAY
    )

    assert any(rule.rule == "cid_in_reference_table" and not rule.passed for rule in rules)


def reconfigured(tmp_path, change) -> Catalog:
    shipped = json.loads(CATALOG.read_text(encoding="utf-8"))
    change(shipped)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(shipped), encoding="utf-8")
    return load_catalog(path)


def test_the_rules_follow_the_configured_tables_not_a_table_in_the_code(tmp_path) -> None:
    """Same code, another customer's vocabulary and protocol format: the rules follow the file."""

    def change(shipped: dict) -> None:
        assessment = shipped["document_types"]["medical_assessment_result"]
        assessment["outcomes"] = {"aprovado": "granted", "negado": "denied"}
        assessment["protocol_pattern"] = "AV/[0-9]{6}"

    catalog = reconfigured(tmp_path, change)
    spec = catalog.types[DocumentType.MEDICAL_ASSESSMENT_RESULT]

    rules = validate(spec, catalog, {"protocol_number": "AV/123456", "outcome": "denied"}, TODAY)

    assert all(rule.passed for rule in rules)
    assert {rule.rule for rule in rules} >= {"protocol_number_format", "outcome_is_categorical"}


def test_which_field_must_not_be_guessed_is_configuration(tmp_path) -> None:
    def change(shipped: dict) -> None:
        shipped["document_types"]["medical_certificate"]["critical"] = ["cid"]

    spec = reconfigured(tmp_path, change).types[DocumentType.MEDICAL_CERTIFICATE]

    assert threshold_for(spec, "cid") == CRITICAL_THRESHOLD
    assert threshold_for(spec, "leave_period") == DEFAULT_THRESHOLD


def test_a_type_outside_the_published_contract_cannot_be_configured_in(tmp_path) -> None:
    """The honest cost of a new document type, written down as a test.

    Fields, critical field, vocabulary and norm terms are configuration and change without a
    release. The *name* is not: it is a value of an enum the published contract pins, so a third
    type costs a contract version as well. Configuring one in silently would let the service answer
    with a `document_type` its own consumers are not required to understand.
    """

    def change(shipped: dict) -> None:
        shipped["document_types"]["aso"] = {"fields": ["conclusion"], "critical": ["conclusion"]}

    with pytest.raises(ValueError, match="aso"):
        reconfigured(tmp_path, change)
