import argparse
import hashlib
import json
import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from html import escape
from pathlib import Path
from statistics import median
from string import Template
from time import perf_counter
from typing import Any

from usecases.errors import ServiceError

ROOT = Path(__file__).resolve().parents[2]
TYPES = {
    "atestado_medico": "medical_certificate",
    "resultado_avaliacao_medica": "medical_assessment_result",
}
FIELD_NAMES = {
    "paciente_nome": "patient_name",
    "paciente_documento": "patient_document",
    "periodo_afastamento": "leave_period",
    "cid": "cid",
    "medico_nome": "doctor_name",
    "crm": "crm",
    "cnes": "cnes",
    "data_emissao": "issue_date",
    "protocolo": "protocol_number",
    "requerente_nome": "requester_name",
    "requerente_documento": "requester_document",
    "tipo_avaliacao": "assessment_type",
    "data_avaliacao": "assessment_date",
    "desfecho": "outcome",
    "periodo_concedido": "granted_period",
}
HIGHER_IS_BETTER = {
    "precision",
    "recall",
    "f1",
    "accuracy",
    "classification_accuracy",
    "refusal_accuracy",
    "outcome_accuracy",
}
LOWER_IS_BETTER = {"abstention_rate", "missing_rate", "review_rate"}


def normalize_expected_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name == "crm":
        return {"number": value["numero"], "state": value["uf"]}
    if name in {"leave_period", "granted_period"}:
        translated = {
            "start": normalize_expected_value("issue_date", value["inicio"]),
            "end": normalize_expected_value("issue_date", value["fim"]),
        }
        if "dias" in value:
            translated["days"] = value["dias"]
        return translated
    if name in {"issue_date", "assessment_date"}:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    if name == "outcome":
        return {"Deferido": "granted", "Indeferido": "denied"}[value]
    return value


def normalize_comparison_value(value: Any) -> Any:
    if isinstance(value, str):
        text = unicodedata.normalize("NFKD", value.casefold())
        return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())
    if isinstance(value, dict):
        return {key: normalize_comparison_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_comparison_value(item) for item in value]
    return value


def ratio_or_none(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def calculate_field_metrics(counts: Counter) -> dict[str, int | float | None]:
    true_positives, false_positives, false_negatives = (
        counts[name] for name in ("true_positive", "false_positive", "false_negative")
    )
    return {
        **{
            name: counts[name]
            for name in (
                "total",
                "true_positive",
                "false_positive",
                "false_negative",
                "correct_null",
                "abstained",
                "missing",
            )
        },
        "precision": ratio_or_none(true_positives, true_positives + false_positives),
        "recall": ratio_or_none(true_positives, true_positives + false_negatives),
        "f1": ratio_or_none(
            2 * true_positives, 2 * true_positives + false_positives + false_negatives
        ),
        "accuracy": ratio_or_none(true_positives + counts["correct_null"], counts["total"]),
        "abstention_rate": ratio_or_none(counts["abstained"], counts["total"]),
        "missing_rate": ratio_or_none(counts["missing"], counts["total"]),
    }


def score_field(expected: Any, actual: dict | None) -> Counter:
    present = actual is not None
    value = actual.get("value") if actual is not None else None
    abstained = bool(actual.get("abstained", False)) if actual is not None else False
    correct = present and normalize_comparison_value(value) == normalize_comparison_value(expected)
    return Counter(
        {
            "total": 1,
            "true_positive": int(correct and expected is not None and not abstained),
            "false_positive": int(value is not None and (not correct or abstained)),
            "false_negative": int(expected is not None and (not correct or abstained)),
            "correct_null": int(correct and expected is None and not abstained),
            "abstained": int(abstained),
            "missing": int(not present),
        }
    )


def calculate_usage_cost_usd(consumption: dict, model_id: str, prices: dict) -> float:
    model = prices.get("models", {}).get(model_id)
    if model is None:
        raise ValueError(f"no price for model {model_id!r} in evals/prices.json")
    return (
        consumption["input_tokens"] * model["input_usd_per_million_tokens"] / 1_000_000
        + consumption["output_tokens"] * model["output_usd_per_million_tokens"] / 1_000_000
        + consumption["ocr_pages"] * prices["ocr_usd_per_page"]
    )


def evaluate(
    cases: list[dict],
    samples: Path,
    analyze: Callable[[bytes], dict],
    *,
    profile: str,
    prices: dict | None = None,
) -> dict[str, Any]:
    if profile not in {"fake", "aws"}:
        raise ValueError("evaluation profile must be fake or aws")
    uses_reference_fakes = profile == "fake"
    filenames = [case["arquivo"] for case in cases]
    if not filenames or len(set(filenames)) != len(filenames):
        raise ValueError("evaluation requires a nonempty set of distinct filenames")
    field_counts: dict[str, Counter] = defaultdict(Counter)
    format_counts: dict[str, Counter] = defaultdict(Counter)
    summary: Counter = Counter(
        {
            "case_count": 0,
            "correct_outcome": 0,
            "classification_count": 0,
            "correct_classification": 0,
            "successful_count": 0,
            "review_count": 0,
            "refusal_count": 0,
            "correct_refusal": 0,
        }
    )
    model_ids, prompt_versions = set(), set()
    durations_seconds = []
    document_costs_usd = []

    for case in cases:
        expected_type = TYPES.get(case["tipo_documento"])
        expected_code = (
            "unsupported_document_type"
            if expected_type is None
            else "invalid_input"
            if case["resultado_esperado"] == "recusa"
            else None
        )
        content = (samples / case["arquivo"]).read_bytes()
        started_at = perf_counter()
        result: dict = {}
        error_code = None
        try:
            result = analyze(content)
        except ServiceError as error:
            error_code = error.code.value
        durations_seconds.append(perf_counter() - started_at)
        classified_type = result.get("document_type", {}).get("value")
        correct_outcome = (
            error_code == expected_code
            if expected_code
            else error_code is None and classified_type == expected_type
        )
        summary["case_count"] += 1
        summary["correct_outcome"] += int(correct_outcome)
        if expected_code != "invalid_input":
            summary["classification_count"] += 1
            summary["correct_classification"] += int(correct_outcome)
        if expected_code:
            summary["refusal_count"] += 1
            summary["correct_refusal"] += int(correct_outcome)
        if result:
            summary["successful_count"] += 1
            summary["review_count"] += int(result.get("review", {}).get("required", False))
            provenance = result.get("provenance", {})
            model_ids.add(provenance.get("model_id", "unknown"))
            prompt_versions.add(provenance.get("prompt_version", "unknown"))
            if not uses_reference_fakes:
                document_costs_usd.append(
                    calculate_usage_cost_usd(
                        result["consumption"], provenance.get("model_id"), prices or {}
                    )
                )

        expected = (
            {
                FIELD_NAMES[name]: normalize_expected_value(FIELD_NAMES[name], value)
                for name, value in case["campos"].items()
            }
            if expected_code is None
            else {}
        )
        actual = result.get("fields", {})
        format_counts.setdefault(case["formato"], Counter())
        for name in sorted(expected.keys() | actual.keys()):
            observed = actual.get(name) if classified_type == expected_type else None
            counts = score_field(expected.get(name), observed)
            field_counts[f"{expected_type or 'unsupported'}.{name}"].update(counts)
            format_counts[case["formato"]].update(counts)

    dataset_sha256 = hashlib.sha256(
        json.dumps(
            sorted(cases, key=lambda case: case["arquivo"]), sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    return {
        "report_version": 1,
        "profile": profile,
        "synthetic": uses_reference_fakes,
        "purpose": "synthetic_pipeline_regression"
        if uses_reference_fakes
        else "model_quality_evaluation",
        "dataset_sha256": dataset_sha256,
        "cases": sorted(filenames),
        "model_ids": sorted(model_ids),
        "prompt_versions": sorted(prompt_versions),
        "cost_components": ["model_tokens", "ocr_pages"],
        "summary": {
            **dict(summary),
            "classification_accuracy": ratio_or_none(
                summary["correct_classification"], summary["classification_count"]
            ),
            "refusal_accuracy": ratio_or_none(summary["correct_refusal"], summary["refusal_count"]),
            "outcome_accuracy": ratio_or_none(summary["correct_outcome"], summary["case_count"]),
            "review_rate": ratio_or_none(summary["review_count"], summary["successful_count"]),
            "local_latency_p50_seconds": median(durations_seconds),
            "local_latency_p95_seconds": sorted(durations_seconds)[
                math.ceil(len(durations_seconds) * 0.95) - 1
            ],
            "aws_latency_p95_seconds": None
            if uses_reference_fakes
            else sorted(durations_seconds)[math.ceil(len(durations_seconds) * 0.95) - 1],
            "mean_cost_usd": sum(document_costs_usd) / len(document_costs_usd)
            if document_costs_usd
            else None,
        },
        "fields": {
            name: calculate_field_metrics(counts) for name, counts in sorted(field_counts.items())
        },
        "formats": {
            name: calculate_field_metrics(counts) for name, counts in sorted(format_counts.items())
        },
    }


def compare_baseline(report: dict, baseline: dict) -> list[str]:
    failures = []
    for key in ("report_version", "profile", "synthetic", "purpose", "dataset_sha256", "cases"):
        if report.get(key) != baseline.get(key):
            failures.append(f"incompatible {key}")
    for group in ("fields", "formats"):
        if report.get(group, {}).keys() != baseline.get(group, {}).keys():
            failures.append(f"changed {group}")

    metric_groups = [("summary", report.get("summary", {}), baseline.get("summary", {}))]
    for group in ("fields", "formats"):
        metric_groups.extend(
            (f"{group}.{name}", report.get(group, {}).get(name, {}), values)
            for name, values in baseline.get(group, {}).items()
        )
    for name, current, previous in metric_groups:
        for metric in sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER):
            baseline_value = previous.get(metric)
            if baseline_value is None:
                continue
            current_value = current.get(metric)
            if (
                current_value is None
                or not isinstance(current_value, (int, float))
                or not math.isfinite(current_value)
            ):
                failures.append(f"missing metric {name}.{metric}")
                continue
            regression = (
                baseline_value - current_value
                if metric in HIGHER_IS_BETTER
                else current_value - baseline_value
            )
            if regression > 0.02 + 1e-12:
                failures.append(
                    f"regression {name}.{metric}: {baseline_value:.6f} -> {current_value:.6f}"
                )
    return failures


def write_reports(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (output / "report.json").write_text(serialized, encoding="utf-8")
    notice = (
        "Regressão sintética de integração. Os cassetes derivam do gabarito: estes números não "
        "demonstram qualidade real do modelo, custo ou latência AWS."
        if report["synthetic"]
        else "Avaliação com serviços reais. Custo não instrumentado; "
        "nenhuma meta de custo foi comprovada."
    )
    page = Template("""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Avaliação de documentos</title>
<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1rem}</style>
<h1>Avaliação de documentos</h1><p>$notice</p>
<p>Precisão e recall sem denominador aparecem como null; nulo correto conta apenas na acurácia.
Latência local não comprova o alvo de homologação.
Regressão permitida: até 2 pontos percentuais.</p>
<h2>Métricas por campo e formato</h2><pre>$report</pre></html>
""")
    (output / "report.html").write_text(
        page.substitute(notice=escape(notice), report=escape(serialized)), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the reference set; fake scores are synthetic."
    )
    parser.add_argument("--profile", choices=("fake", "aws"), default="fake")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports")
    args = parser.parse_args(argv)

    from entrypoints.bootstrap import build_analyzer
    from entrypoints.http.models import from_analysis

    analyze = build_analyzer(args.profile)

    def analyze_with_usage(content: bytes) -> dict:
        analysis = analyze(content)
        return {
            **from_analysis(analysis).model_dump(mode="json"),
            "consumption": {
                "input_tokens": analysis.model_usage.input_tokens,
                "output_tokens": analysis.model_usage.output_tokens,
                "ocr_pages": analysis.pages_read,
            },
        }

    cases = json.loads((ROOT / "samples/answer_key.json").read_text(encoding="utf-8"))
    prices = (
        json.loads((ROOT / "evals/prices.json").read_text(encoding="utf-8"))
        if args.profile == "aws"
        else None
    )
    report = evaluate(
        cases, ROOT / "samples", analyze_with_usage, profile=args.profile, prices=prices
    )
    regressions = (
        compare_baseline(report, json.loads(args.baseline.read_text(encoding="utf-8")))
        if args.baseline
        else []
    )
    report["regressions"] = regressions
    write_reports(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return int(bool(regressions))


if __name__ == "__main__":
    raise SystemExit(main())
