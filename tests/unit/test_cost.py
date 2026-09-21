from dataclasses import replace
from pathlib import Path

import pytest

from adapters.fakes.llm import StubLlm
from core.analysis import TokenUsage
from entrypoints.bootstrap import FAKE, build_analyzer, build_dependencies
from usecases.errors import ErrorCode, ServiceError

ROOT = Path(__file__).resolve().parents[2]
PRICES = {
    "models": {
        "model-a": {"input_usd_per_million_tokens": 5.0, "output_usd_per_million_tokens": 25.0}
    },
    "ocr_usd_per_page": 0.0015,
}


class CountingLlm(StubLlm):
    def classify(self, pages):
        return replace(super().classify(pages), usage=TokenUsage(1000, 10))

    def extract(self, pages, document_type, prompt_version):
        extraction = super().extract(pages, document_type, prompt_version)
        return replace(extraction, usage=TokenUsage(3000, 500))


def case(filename, document_type="atestado_medico"):
    return {
        "arquivo": filename,
        "tipo_documento": document_type,
        "formato": "pdf_nativo",
        "resultado_esperado": "extracao_completa",
        "campos": {},
    }


def analysed(input_tokens, output_tokens, ocr_pages, model_id="model-a"):
    return {
        "document_type": {"value": "medical_certificate"},
        "fields": {},
        "review": {"required": False},
        "provenance": {"model_id": model_id, "prompt_version": "v1"},
        "consumption": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "ocr_pages": ocr_pages,
        },
    }


def evaluate_aws(tmp_path, cases, outcomes):
    from evals.run import evaluate

    for item in cases:
        (tmp_path / item["arquivo"]).write_bytes(b"synthetic")
    pending = iter(outcomes)

    def analyze(_):
        outcome = next(pending)
        if outcome is None:
            raise ServiceError(ErrorCode.UNSUPPORTED_DOCUMENT_TYPE, "unsupported")
        return outcome

    return evaluate(cases, tmp_path, analyze, profile="aws", prices=PRICES)


def test_the_analysis_adds_up_the_tokens_of_classification_and_extraction():
    dependencies = replace(build_dependencies(FAKE), llm=CountingLlm())
    content = (ROOT / "samples/atestado_01_pdf_nativo.pdf").read_bytes()

    analysis = build_analyzer(dependencies=dependencies)(content)

    assert analysis.model_usage == TokenUsage(input_tokens=4000, output_tokens=510)


def test_aws_evaluation_reports_the_mean_variable_cost_of_analysed_documents(tmp_path):
    cases = [case("a.pdf"), case("b.pdf"), case("c.pdf", "fora_do_escopo")]
    outcomes = [analysed(1_000_000, 0, 0), analysed(0, 100_000, 10), None]

    report = evaluate_aws(tmp_path, cases, outcomes)

    assert report["summary"]["mean_cost_usd"] == pytest.approx((5.0 + 2.515) / 2)
    assert report["cost_components"] == ["model_tokens", "ocr_pages"]


def test_a_model_without_a_price_stops_the_evaluation(tmp_path):
    with pytest.raises(ValueError, match="model-z"):
        evaluate_aws(tmp_path, [case("a.pdf")], [analysed(10, 10, 0, model_id="model-z")])
