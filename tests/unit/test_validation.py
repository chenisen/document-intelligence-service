from datetime import date

import pytest

from core import validation
from core.catalog import Catalog, DocumentTypeSpec

TODAY = date(2026, 9, 18)

CATALOG = Catalog(types={}, cid_codes=frozenset({"J11", "M54.5"}), reference_tables_version="test")
CERTIFICATE = DocumentTypeSpec(
    fields=("issue_date", "leave_period", "crm", "cid"), critical=frozenset({"leave_period"})
)
ASSESSMENT = DocumentTypeSpec(
    fields=("outcome", "granted_period", "protocol_number", "assessment_date", "issue_date"),
    critical=frozenset({"outcome"}),
    outcomes={"deferido": "granted", "indeferido": "denied"},
    denied_outcome="denied",
    protocol_pattern="[0-9]{4}-AV-[0-9]{7}",
)


@pytest.mark.parametrize(
    ("name", "value", "rule_name"),
    [
        ("issue_date", "14/09/2026", "issue_date_is_readable"),
        ("outcome", "Deferido", "outcome_is_categorical"),
    ],
)
def test_values_outside_the_contract_vocabulary_fail_instead_of_being_repaired(
    name, value, rule_name
):
    rules = validation.validate(ASSESSMENT, CATALOG, {name: value}, TODAY)

    assert any(rule.rule == rule_name and not rule.passed for rule in rules)


def test_valid_canonical_medical_certificate_passes_integrity_rules():
    values = {
        "issue_date": "2026-09-14",
        "leave_period": {"days": 3, "start": "2026-09-14", "end": "2026-09-16"},
        "crm": {"number": "999001", "state": "SP"},
        "cid": "J11",
    }

    rules = validation.validate(CERTIFICATE, CATALOG, values, TODAY)

    assert rules
    assert all(rule.passed for rule in rules)


@pytest.mark.parametrize(
    ("values", "rule_name", "field"),
    [
        ({"issue_date": "2026-09-19"}, "issue_date_not_in_the_future", "issue_date"),
        ({"issue_date": "31/02/2026"}, "issue_date_is_readable", "issue_date"),
        ({"issue_date": 12}, "issue_date_is_readable", "issue_date"),
        ({"crm": "999001/SP"}, "crm_format", "crm"),
        ({"crm": {"number": "12", "state": "SP"}}, "crm_format", "crm"),
        ({"crm": {"number": "999001", "state": "SPO"}}, "crm_format", "crm"),
        ({"cid": "UNKNOWN"}, "cid_in_reference_table", "cid"),
        ({"leave_period": "3 dias"}, "leave_period_format", "leave_period"),
        ({"leave_period": []}, "leave_period_format", "leave_period"),
        (
            {"leave_period": {"days": 3, "start": "2026-09-16", "end": "2026-09-14"}},
            "leave_period_end_not_before_start",
            "leave_period",
        ),
        (
            {"leave_period": {"days": 4, "start": "2026-09-14", "end": "2026-09-16"}},
            "leave_period_days_match_dates",
            "leave_period",
        ),
        (
            {"leave_period": {"days": 3, "start": "bad", "end": "2026-09-16"}},
            "leave_period_dates_are_readable",
            "leave_period",
        ),
    ],
)
def test_malformed_or_inconsistent_fields_fail_without_crashing(values, rule_name, field):
    rules = validation.validate(CERTIFICATE, CATALOG, values, TODAY)

    assert any(rule.rule == rule_name and not rule.passed for rule in rules)
    assert field in validation.failed_fields(rules)


@pytest.mark.parametrize("days", [-1, 0, True, 1.0, "1"])
def test_period_days_must_be_a_positive_integer(days):
    values = {"leave_period": {"days": days, "start": "2026-09-14", "end": "2026-09-14"}}

    rules = validation.validate(CERTIFICATE, CATALOG, values, TODAY)

    assert any(rule.rule == "leave_period_days_are_positive" and not rule.passed for rule in rules)


@pytest.mark.parametrize("outcome", ["granted", "denied"])
def test_canonical_assessment_outcomes_and_chronological_dates_pass(outcome):
    values = {
        "outcome": outcome,
        "protocol_number": "2026-AV-0001234",
        "assessment_date": "2026-09-13",
        "issue_date": "2026-09-14",
        "granted_period": None,
    }

    rules = validation.validate(ASSESSMENT, CATALOG, values, TODAY)

    assert all(rule.passed for rule in rules)
    assert any(rule.rule == "assessment_date_not_after_issue_date" for rule in rules)


@pytest.mark.parametrize(
    ("values", "rule_name", "field"),
    [
        ({"outcome": "maybe"}, "outcome_is_categorical", "outcome"),
        ({"protocol_number": "invalid"}, "protocol_number_format", "protocol_number"),
        ({"assessment_date": "31/02/2026"}, "assessment_date_is_readable", "assessment_date"),
        (
            {"assessment_date": "2026-09-15", "issue_date": "2026-09-14"},
            "assessment_date_not_after_issue_date",
            "assessment_date",
        ),
        (
            {"outcome": "denied", "granted_period": {"days": 1}},
            "denied_assessment_has_no_granted_period",
            "granted_period",
        ),
    ],
)
def test_assessment_integrity_failures_identify_the_field(values, rule_name, field):
    rules = validation.validate(ASSESSMENT, CATALOG, values, TODAY)

    assert any(rule.rule == rule_name and not rule.passed for rule in rules)
    assert field in validation.failed_fields(rules)


def test_absent_optional_fields_are_not_reported_as_invalid():
    assert validation.validate(CERTIFICATE, CATALOG, {"crm": None}, TODAY) == []
