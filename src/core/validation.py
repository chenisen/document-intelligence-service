"""Deterministic integrity rules. No model involved.

Spec 0004, rules 1 to 4. A failed rule lowers the field's confidence and puts a reason in the review
block, so a person looks at it. It never fails the analysis.

The rules here are code because they are arithmetic and shape: a period that ends before it
starts is wrong in any catalogue. The tables they read are content and come from the catalogue:
which CID codes exist, which words mean granted, how a protocol number is spelled. There is no `if`
by document type in this module; a rule runs when the field it is about belongs to the type.
"""

import re
from dataclasses import dataclass
from datetime import date

from core.catalog import Catalog, DocumentTypeSpec

CRM_NUMBER = re.compile(r"[0-9]{4,7}")
STATE = re.compile(r"[A-Z]{2}")


@dataclass(frozen=True)
class Validation:
    rule: str
    passed: bool
    detail: str | None = None
    field: str | None = None


def _parse(value: object) -> date | None:
    """Dates arrive in the contract's vocabulary. Repairing another format here would hide a
    prompt that stopped honouring the schema, which is exactly what has to reach a person."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _period(rules: list[Validation], name: str, period: object) -> None:
    if period is None:
        return
    if not isinstance(period, dict):
        rules.append(Validation(f"{name}_format", False, field=name))
        return
    if "days" in period:
        days = period["days"]
        rules.append(
            Validation(f"{name}_days_are_positive", type(days) is int and days > 0, field=name)
        )
    start, end = _parse(period.get("start")), _parse(period.get("end"))
    if start is None or end is None:
        rules.append(Validation(f"{name}_dates_are_readable", False, "unparseable date", name))
        return
    rules.append(Validation(f"{name}_end_not_before_start", end >= start, field=name))
    if "days" in period:
        expected = (end - start).days + 1
        rules.append(
            Validation(
                f"{name}_days_match_dates",
                period["days"] == expected,
                "declared days must match the inclusive date interval",
                name,
            )
        )


def validate(
    spec: DocumentTypeSpec, catalog: Catalog, values: dict[str, object], today: date
) -> list[Validation]:
    rules: list[Validation] = []

    issue_date = values.get("issue_date")
    issued = _parse(issue_date)
    if issue_date is not None and issued is None:
        rules.append(Validation("issue_date_is_readable", False, field="issue_date"))
    if issued is not None:
        rules.append(
            Validation("issue_date_not_in_the_future", issued <= today, field="issue_date")
        )

    crm = values.get("crm")
    if crm is not None:
        ok = (
            isinstance(crm, dict)
            and isinstance(crm.get("number"), str)
            and bool(CRM_NUMBER.fullmatch(crm["number"]))
            and isinstance(crm.get("state"), str)
            and bool(STATE.fullmatch(crm["state"]))
        )
        rules.append(Validation("crm_format", ok, field="crm"))

    cid = values.get("cid")
    if cid is not None:
        rules.append(
            Validation("cid_in_reference_table", str(cid) in catalog.cid_codes, field="cid")
        )

    _period(rules, "leave_period", values.get("leave_period"))

    outcome = values.get("outcome")
    if outcome is not None:
        rules.append(
            Validation(
                "outcome_is_categorical",
                outcome in set(spec.outcomes.values()),
                field="outcome",
            )
        )

    granted = values.get("granted_period")
    if spec.denied_outcome is not None and outcome == spec.denied_outcome:
        rules.append(
            Validation(
                "denied_assessment_has_no_granted_period", granted is None, field="granted_period"
            )
        )
    _period(rules, "granted_period", granted)

    protocol = values.get("protocol_number")
    if protocol is not None and spec.protocol_pattern is not None:
        rules.append(
            Validation(
                "protocol_number_format",
                isinstance(protocol, str) and bool(re.fullmatch(spec.protocol_pattern, protocol)),
                field="protocol_number",
            )
        )

    assessment_date = values.get("assessment_date")
    assessed = _parse(assessment_date)
    if assessment_date is not None and assessed is None:
        rules.append(Validation("assessment_date_is_readable", False, field="assessment_date"))
    if assessed is not None and issued is not None:
        rules.append(
            Validation(
                "assessment_date_not_after_issue_date", assessed <= issued, field="assessment_date"
            )
        )

    return rules


def failed_fields(rules: list[Validation]) -> set[str]:
    return {rule.field for rule in rules if not rule.passed and rule.field is not None}
