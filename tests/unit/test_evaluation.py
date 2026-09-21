import copy
import json
from pathlib import Path

import pytest

from usecases.errors import ErrorCode, ServiceError

ROOT = Path(__file__).resolve().parents[2]


def golden_case(filename="case.pdf", fields=None, source_format="pdf_nativo"):
    return {
        "arquivo": filename,
        "tipo_documento": "atestado_medico",
        "formato": source_format,
        "resultado_esperado": "extracao_completa",
        "campos": fields or {"paciente_nome": "Ana"},
    }


def response(fields, document_type="medical_certificate", review=False):
    return {
        "document_type": {"value": document_type},
        "fields": fields,
        "review": {"required": review},
        "provenance": {"model_id": "stub/reference-set", "prompt_version": "v1"},
    }


def field(value, abstained=False):
    return {"value": value, "abstained": abstained}


def run_cases(tmp_path, cases, responses):
    from evals.run import evaluate

    for case in cases:
        (tmp_path / case["arquivo"]).write_bytes(b"synthetic")
    results = iter(responses)
    return evaluate(cases, tmp_path, lambda _: next(results), profile="fake")


def test_evaluation_counts_classification_and_refusals():
    from evals.run import evaluate

    cases = json.loads((ROOT / "samples/answer_key.json").read_text())
    pending = iter(cases)
    seen = []

    def analyze(content):
        case = next(pending)
        seen.append(len(content))
        if case["tipo_documento"] in {"aso", "fora_do_escopo"}:
            raise ServiceError(ErrorCode.UNSUPPORTED_DOCUMENT_TYPE, "unsupported")
        kind = (
            "medical_certificate"
            if case["tipo_documento"] == "atestado_medico"
            else "medical_assessment_result"
        )
        return response({}, kind)

    refusals = sum(case["tipo_documento"] in {"aso", "fora_do_escopo"} for case in cases)

    report = evaluate(cases, ROOT / "samples", analyze, profile="fake")

    assert len(seen) == report["summary"]["case_count"] == len(cases)
    assert report["summary"]["classification_count"] == len(cases)
    assert report["summary"]["classification_accuracy"] == 1.0
    assert report["summary"]["refusal_count"] == refusals
    assert report["summary"]["refusal_accuracy"] == (1.0 if refusals else None)
    assert report["summary"]["outcome_accuracy"] == 1.0


def test_evaluation_scores_fields_and_formats_without_null_inflation(tmp_path):
    cases = [
        golden_case(f"{index}.pdf", {"paciente_nome": "Ana", "cid": cid})
        for index, cid in enumerate([None, None, "J11", None])
    ]
    report = run_cases(
        tmp_path,
        cases,
        [
            response({"patient_name": field("Ana"), "cid": field(None)}),
            response({"patient_name": field("Other"), "cid": field("J11")}),
            response({"patient_name": field(None, True), "cid": field(None, True)}),
            response({}),
        ],
    )
    name = report["fields"]["medical_certificate.patient_name"]
    assert (name["true_positive"], name["false_positive"], name["false_negative"]) == (1, 1, 3)
    assert name["precision"] == 0.5
    assert name["recall"] == 0.25
    assert name["f1"] == pytest.approx(1 / 3)
    assert name["accuracy"] == name["abstention_rate"] == name["missing_rate"] == 0.25
    cid = report["fields"]["medical_certificate.cid"]
    assert cid["correct_null"] == 1
    assert cid["false_positive"] == 1
    assert cid["false_negative"] == 1
    assert report["formats"]["pdf_nativo"]["total"] == 8
    assert report["formats"]["pdf_nativo"]["accuracy"] == 0.25


def test_expected_null_is_measured_without_inventing_precision(tmp_path):
    report = run_cases(
        tmp_path,
        [golden_case(fields={"cid": None})],
        [response({"cid": field(None)})],
    )
    metrics = report["fields"]["medical_certificate.cid"]
    assert metrics["precision"] is metrics["recall"] is metrics["f1"] is None
    assert metrics["accuracy"] == 1.0
    assert metrics["abstention_rate"] == 0.0


def test_evaluation_translates_golden_fields_to_contract_values(tmp_path):
    case = golden_case(
        fields={
            "paciente_nome": "Ána   MARQUES",
            "crm": {"numero": "999001", "uf": "SP"},
            "periodo_afastamento": {"inicio": "14/09/2026", "fim": "16/09/2026", "dias": 3},
            "data_emissao": "14/09/2026",
        }
    )
    assessment = {
        **golden_case("assessment.pdf", {"desfecho": "Indeferido", "periodo_concedido": None}),
        "tipo_documento": "resultado_avaliacao_medica",
    }
    report = run_cases(
        tmp_path,
        [case, assessment],
        [
            response(
                {
                    "patient_name": field("ana marques"),
                    "crm": field({"number": "999001", "state": "SP"}),
                    "leave_period": field({"start": "2026-09-14", "end": "2026-09-16", "days": 3}),
                    "issue_date": field("2026-09-14"),
                }
            ),
            response(
                {"outcome": field("denied"), "granted_period": field(None)},
                "medical_assessment_result",
            ),
        ],
    )
    assert all(metrics["accuracy"] == 1.0 for metrics in report["fields"].values())


def test_unexpected_refusal_is_scored_as_missing_extraction(tmp_path):
    from evals.run import evaluate

    (tmp_path / "case.pdf").write_bytes(b"synthetic")

    def analyze(_):
        raise ServiceError(ErrorCode.UPSTREAM_TIMEOUT, "unavailable")

    report = evaluate([golden_case()], tmp_path, analyze, profile="fake")
    assert report["summary"]["classification_accuracy"] == 0.0
    assert report["summary"]["outcome_accuracy"] == 0.0
    assert report["fields"]["medical_certificate.patient_name"]["recall"] == 0.0
    assert report["fields"]["medical_certificate.patient_name"]["missing_rate"] == 1.0


def test_fake_evaluation_is_explicitly_synthetic(tmp_path):
    report = run_cases(tmp_path, [golden_case()], [response({"patient_name": field("Ana")})])
    assert report["synthetic"] is True
    assert report["purpose"] == "synthetic_pipeline_regression"
    assert report["model_ids"] == ["stub/reference-set"]
    assert report["prompt_versions"] == ["v1"]
    assert report["summary"]["aws_latency_p95_seconds"] is None
    assert report["summary"]["mean_cost_usd"] is None


@pytest.mark.parametrize(
    ("metric", "old", "current", "fails"),
    [
        ("f1", 0.95, 0.93, False),
        ("f1", 0.95, 0.9299, True),
        ("abstention_rate", 0.10, 0.12, False),
        ("abstention_rate", 0.10, 0.1201, True),
        ("abstention_rate", 0.10, 0.05, False),
        ("missing_rate", 0.0, 0.03, True),
    ],
)
def test_regression_gate_handles_metric_direction_and_two_point_boundary(
    tmp_path, metric, old, current, fails
):
    from evals.run import compare_baseline

    baseline = run_cases(tmp_path, [golden_case()], [response({"patient_name": field("Ana")})])
    report = copy.deepcopy(baseline)
    baseline["fields"]["medical_certificate.patient_name"][metric] = old
    report["fields"]["medical_certificate.patient_name"][metric] = current
    assert bool(compare_baseline(report, baseline)) is fails


@pytest.mark.parametrize("change", ["case", "field", "format", "modality", "metric", "golden"])
def test_regression_gate_rejects_lost_cases_fields_formats_and_modalities(tmp_path, change):
    from evals.run import compare_baseline

    baseline = run_cases(tmp_path, [golden_case()], [response({"patient_name": field("Ana")})])
    report = copy.deepcopy(baseline)
    if change == "case":
        report["cases"].clear()
    elif change == "field":
        report["fields"].clear()
    elif change == "format":
        report["formats"]["png"] = report["formats"].pop("pdf_nativo")
    elif change == "modality":
        report["synthetic"] = False
        report["profile"] = "aws"
    elif change == "metric":
        report["fields"]["medical_certificate.patient_name"]["f1"] = None
    else:
        report["dataset_sha256"] = "changed"
    assert compare_baseline(report, baseline)


def test_evaluation_reports_never_include_extracted_values(tmp_path):
    from evals.run import write_reports

    marker = "SECRET-PATIENT-12345"
    report = run_cases(
        tmp_path,
        [golden_case("<case>.pdf", {"paciente_nome": marker})],
        [response({"patient_name": {**field(marker), "evidence": {"text": marker}}})],
    )
    write_reports(report, tmp_path / "report")
    output = (tmp_path / "report/report.html").read_text()
    assert "&lt;case&gt;.pdf" in output
    assert "<case>.pdf" not in output
    assert "sintética" in output
    assert "qualidade" in output
    assert marker not in output
    assert marker not in (tmp_path / "report/report.json").read_text()
