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


def _parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validate_period(validations: list[Validation], name: str, period: object) -> None:
    if period is None:
        return
    if not isinstance(period, dict):
        validations.append(Validation(f"{name}_format", False, field=name))
        return
    if "days" in period:
        days = period["days"]
        validations.append(
            Validation(f"{name}_days_are_positive", type(days) is int and days > 0, field=name)
        )
    start, end = _parse_iso_date(period.get("start")), _parse_iso_date(period.get("end"))
    if start is None or end is None:
        validations.append(
            Validation(f"{name}_dates_are_readable", False, "unparseable date", name)
        )
        return
    validations.append(Validation(f"{name}_end_not_before_start", end >= start, field=name))
    if "days" in period:
        inclusive_days = (end - start).days + 1
        validations.append(
            Validation(
                f"{name}_days_match_dates",
                period["days"] == inclusive_days,
                "declared days must match the inclusive date interval",
                name,
            )
        )


def validate(
    spec: DocumentTypeSpec, catalog: Catalog, values: dict[str, object], today: date
) -> list[Validation]:
    validations: list[Validation] = []

    issue_date = values.get("issue_date")
    parsed_issue_date = _parse_iso_date(issue_date)
    if issue_date is not None and parsed_issue_date is None:
        validations.append(Validation("issue_date_is_readable", False, field="issue_date"))
    if parsed_issue_date is not None:
        validations.append(
            Validation(
                "issue_date_not_in_the_future", parsed_issue_date <= today, field="issue_date"
            )
        )

    crm = values.get("crm")
    if crm is not None:
        has_valid_crm_format = (
            isinstance(crm, dict)
            and isinstance(crm.get("number"), str)
            and bool(CRM_NUMBER.fullmatch(crm["number"]))
            and isinstance(crm.get("state"), str)
            and bool(STATE.fullmatch(crm["state"]))
        )
        validations.append(Validation("crm_format", has_valid_crm_format, field="crm"))

    cid = values.get("cid")
    if cid is not None:
        validations.append(
            Validation("cid_in_reference_table", str(cid) in catalog.cid_codes, field="cid")
        )

    _validate_period(validations, "leave_period", values.get("leave_period"))

    outcome = values.get("outcome")
    if outcome is not None:
        validations.append(
            Validation(
                "outcome_is_categorical",
                outcome in set(spec.outcomes.values()),
                field="outcome",
            )
        )

    granted_period = values.get("granted_period")
    if spec.denied_outcome is not None and outcome == spec.denied_outcome:
        validations.append(
            Validation(
                "denied_assessment_has_no_granted_period",
                granted_period is None,
                field="granted_period",
            )
        )
    _validate_period(validations, "granted_period", granted_period)

    protocol_number = values.get("protocol_number")
    if protocol_number is not None and spec.protocol_pattern is not None:
        validations.append(
            Validation(
                "protocol_number_format",
                isinstance(protocol_number, str)
                and bool(re.fullmatch(spec.protocol_pattern, protocol_number)),
                field="protocol_number",
            )
        )

    assessment_date = values.get("assessment_date")
    parsed_assessment_date = _parse_iso_date(assessment_date)
    if assessment_date is not None and parsed_assessment_date is None:
        validations.append(
            Validation("assessment_date_is_readable", False, field="assessment_date")
        )
    if parsed_assessment_date is not None and parsed_issue_date is not None:
        validations.append(
            Validation(
                "assessment_date_not_after_issue_date",
                parsed_assessment_date <= parsed_issue_date,
                field="assessment_date",
            )
        )

    return validations


def failed_fields(validations: list[Validation]) -> set[str]:
    return {rule.field for rule in validations if not rule.passed and rule.field is not None}
