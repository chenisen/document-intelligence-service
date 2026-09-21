"""Evaluate the reference set without retaining analysis results or document contents.

No perfil `fake` os dublês respondem a partir do próprio gabarito, então estes números medem
regressão de integração, nunca qualidade de modelo. Medir qualidade exige o perfil `aws`.
"""

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


def golden_value(name: str, value: Any) -> Any:
    """Translate the answer key independently of the cassette generator."""
    if value is None:
        return None
    if name == "crm":
        return {"number": value["numero"], "state": value["uf"]}
    if name in {"leave_period", "granted_period"}:
        translated = {
            "start": golden_value("issue_date", value["inicio"]),
            "end": golden_value("issue_date", value["fim"]),
        }
        if "dias" in value:
            translated["days"] = value["dias"]
        return translated
    if name in {"issue_date", "assessment_date"}:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    if name == "outcome":
        return {"Deferido": "granted", "Indeferido": "denied"}[value]
    return value


def comparable(value: Any) -> Any:
    if isinstance(value, str):
        text = unicodedata.normalize("NFKD", value.casefold())
        return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return value


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(counts: Counter) -> dict[str, int | float | None]:
    tp, fp, fn = (counts[name] for name in ("true_positive", "false_positive", "false_negative"))
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
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + counts["correct_null"], counts["total"]),
        "abstention_rate": ratio(counts["abstained"], counts["total"]),
        "missing_rate": ratio(counts["missing"], counts["total"]),
    }


def score_field(expected: Any, actual: dict | None) -> Counter:
    present = actual is not None
    value = actual.get("value") if actual is not None else None
    abstained = bool(actual.get("abstained", False)) if actual is not None else False
    correct = present and comparable(value) == comparable(expected)
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


def cost_usd(consumption: dict, model_id: str, prices: dict) -> float:
    """List price of what one analysis consumed. A missing price stops the run: never zero."""
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
    # O perfil decide: no `fake` a resposta vem do gabarito, e comparar o gabarito com ele mesmo
    # não é medição. Antes isto também farejava a string "synthetic" no id do modelo, o que passou a
    # ser ruído quando o id mudou — o perfil sempre foi a informação que importava.
    synthetic = profile == "fake"
    filenames = [case["arquivo"] for case in cases]
    if not filenames or len(set(filenames)) != len(filenames):
        raise ValueError("evaluation requires a nonempty set of distinct filenames")
    field_counts: dict[str, Counter] = defaultdict(Counter)
    format_counts: dict[str, Counter] = defaultdict(Counter)
    # Inicializado com todas as chaves: `dict(Counter())` só materializa o que foi incrementado, e
    # um relatório cuja forma depende dos dados não é comparável com baseline. Conjunto sem recusa
    # precisa reportar `refusal_count: 0`, não omitir a chave.
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
    durations = []
    costs = []

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
        started = perf_counter()
        result: dict = {}
        error_code = None
        try:
            result = analyze(content)
        except ServiceError as error:
            error_code = error.code.value
        durations.append(perf_counter() - started)
        classified = result.get("document_type", {}).get("value")
        correct_outcome = (
            error_code == expected_code
            if expected_code
            else error_code is None and classified == expected_type
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
            if not synthetic:
                costs.append(
                    cost_usd(result["consumption"], provenance.get("model_id"), prices or {})
                )

        expected = (
            {
                FIELD_NAMES[name]: golden_value(FIELD_NAMES[name], value)
                for name, value in case["campos"].items()
            }
            if expected_code is None
            else {}
        )
        actual = result.get("fields", {})
        format_counts[case["formato"]]  # Include formats with only refusal cases.
        for name in sorted(expected.keys() | actual.keys()):
            observed = actual.get(name) if classified == expected_type else None
            counts = score_field(expected.get(name), observed)
            field_counts[f"{expected_type or 'unsupported'}.{name}"].update(counts)
            format_counts[case["formato"]].update(counts)

    digest = hashlib.sha256(
        json.dumps(
            sorted(cases, key=lambda case: case["arquivo"]), sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    return {
        "report_version": 1,
        "profile": profile,
        "synthetic": synthetic,
        "purpose": "synthetic_pipeline_regression" if synthetic else "model_quality_evaluation",
        "dataset_sha256": digest,
        "cases": sorted(filenames),
        "model_ids": sorted(model_ids),
        "prompt_versions": sorted(prompt_versions),
        "cost_components": ["model_tokens", "ocr_pages"],
        "summary": {
            **dict(summary),
            "classification_accuracy": ratio(
                summary["correct_classification"], summary["classification_count"]
            ),
            "refusal_accuracy": ratio(summary["correct_refusal"], summary["refusal_count"]),
            "outcome_accuracy": ratio(summary["correct_outcome"], summary["case_count"]),
            "review_rate": ratio(summary["review_count"], summary["successful_count"]),
            "local_latency_p50_seconds": median(durations),
            "local_latency_p95_seconds": sorted(durations)[math.ceil(len(durations) * 0.95) - 1],
            "aws_latency_p95_seconds": None
            if synthetic
            else sorted(durations)[math.ceil(len(durations) * 0.95) - 1],
            # Dollars, the currency of the price table. Converting to reais for RNF-03 uses the
            # rate of the day and stays out of the report, where a frozen rate would look measured.
            "mean_cost_usd": sum(costs) / len(costs) if costs else None,
        },
        "fields": {name: metrics(counts) for name, counts in sorted(field_counts.items())},
        "formats": {name: metrics(counts) for name, counts in sorted(format_counts.items())},
    }


def compare_baseline(report: dict, baseline: dict) -> list[str]:
    failures = []
    for key in ("report_version", "profile", "synthetic", "purpose", "dataset_sha256", "cases"):
        if report.get(key) != baseline.get(key):
            failures.append(f"incompatible {key}")
    for group in ("fields", "formats"):
        if report.get(group, {}).keys() != baseline.get(group, {}).keys():
            failures.append(f"changed {group}")

    pairs = [("summary", report.get("summary", {}), baseline.get("summary", {}))]
    for group in ("fields", "formats"):
        pairs.extend(
            (f"{group}.{name}", report.get(group, {}).get(name, {}), values)
            for name, values in baseline.get(group, {}).items()
        )
    for name, current, previous in pairs:
        for metric in sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER):
            old = previous.get(metric)
            if old is None:
                continue
            new = current.get(metric)
            if new is None or not isinstance(new, (int, float)) or not math.isfinite(new):
                failures.append(f"missing metric {name}.{metric}")
                continue
            loss = old - new if metric in HIGHER_IS_BETTER else new - old
            if loss > 0.02 + 1e-12:
                failures.append(f"regression {name}.{metric}: {old:.6f} -> {new:.6f}")
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

    def run(content: bytes) -> dict:
        analysis = analyze(content)
        return {
            **from_analysis(analysis).model_dump(mode="json"),
            "consumption": {
                "input_tokens": analysis.model_usage.input_tokens,
                "output_tokens": analysis.model_usage.output_tokens,
                "ocr_pages": analysis.pages_read,
            },
        }

    cases = json.loads((ROOT / "samples/gabarito.json").read_text(encoding="utf-8"))
    prices = (
        json.loads((ROOT / "evals/prices.json").read_text(encoding="utf-8"))
        if args.profile == "aws"
        else None
    )
    report = evaluate(cases, ROOT / "samples", run, profile=args.profile, prices=prices)
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
