"""The published endpoints must execute the pipeline, not a fixed response."""

import hashlib
import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from adapters.fakes.ocr import SpyOcr
from core.analysis import Classification
from core.document import MAX_FILE_BYTES
from core.values import Confidence
from entrypoints.bootstrap import build_analyzer, build_dependencies
from entrypoints.http.app import app, get_dependencies
from usecases.ports import LlmPort

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
client = TestClient(app, raise_server_exceptions=False)
ROUTE = "/v1/documents:analyze"
SCHEMA = Draft202012Validator(
    json.loads((ROOT / "contracts/v1/analysis_result.schema.json").read_text())
)


def analyze(name: str):
    return client.post(ROUTE, files={"file": (name, (SAMPLES / name).read_bytes())})


def test_http_extracts_a_certificate_with_provenance_and_knowledge():
    content = (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()
    response = client.post(ROUTE, files={"file": ("atestado.pdf", content, "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    SCHEMA.validate(body)
    assert body["file_sha256"] == hashlib.sha256(content).hexdigest()
    assert body["fields"]["leave_period"]["value"] == {
        "days": 3,
        "start": "2026-09-14",
        "end": "2026-09-16",
    }
    assert body["capabilities"]["extraction"] == "available"
    configured = json.loads((ROOT / "config/bedrock.json").read_text(encoding="utf-8"))
    assert body["provenance"]["model_id"] == "stub/reference-set"
    assert body["provenance"]["prompt_version"] == configured["prompt_version"]
    assert body["provenance"]["ocr_engine"] == "none/direct-text"
    assert body["capabilities"]["knowledge_enrichment"] == "available"
    assert body["knowledge"], "a certificate with a leave period must reach at least one norm"
    for norm in body["knowledge"]:
        assert norm["source"] and norm["version"] and norm["excerpt"]


def test_http_extracts_denial_without_inventing_a_granted_period():
    response = analyze("resultado_02_indeferido_digitalizado.jpg")
    assert response.status_code == 200
    body = response.json()
    SCHEMA.validate(body)
    assert body["document_type"]["value"] == "medical_assessment_result"
    assert body["fields"]["outcome"]["value"] == "denied"
    assert body["fields"]["granted_period"]["value"] is None


def test_http_sends_a_certificate_without_crm_to_review():
    response = analyze("atestado_06_captura_tela.png")
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["crm"]["value"] is None
    assert "critical_field_missing:crm" in body["review"]["reasons"]


def test_http_refuses_a_document_outside_the_catalogue():
    """Recusar é comportamento do pipeline, e é isso que este teste prova.

    O conjunto de referência só tem os dois tipos do MVP, então a recusa é exercitada injetando um
    modelo que classifica como "nenhum dos suportados". Isso é mais honesto do que o arranjo
    anterior, com um ASO no conjunto: naquele caso o cassete dizia `document_type: null` porque o
    gabarito mandava, então a recusa nunca provou qualidade de classificação — provou que o pipeline
    trata classificação nula. É exatamente o que está provado aqui, sem o documento no meio.

    Qualidade de classificação só a avaliação contra uma conta real prova.
    """

    class UnsupportedLlm(LlmPort):
        def classify(self, pages):
            return Classification(document_type=None, confidence=Confidence(0.93))

        def extract(self, pages, document_type, prompt_version):  # pragma: no cover
            raise AssertionError("não se extrai de documento recusado")

    dependencies = replace(build_dependencies("fake"), llm=UnsupportedLlm())
    app.dependency_overrides[get_dependencies] = lambda: dependencies
    try:
        response = analyze("atestado_01_pdf_nativo.pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_document_type"


def test_the_caller_cannot_inform_the_document_type():
    response = client.post(
        ROUTE,
        files={"file": ("a.pdf", (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes())},
        data={"document_type": "medical_certificate"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_input"


@pytest.mark.parametrize("content", [b"not a document", b"%PDF-broken", b"\x89PNGbroken"])
def test_malformed_documents_return_a_problem(content):
    response = client.post(ROUTE, files={"file": ("document.pdf", content)})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_input"


def test_upload_never_rolls_to_disk(monkeypatch):
    def forbid_disk(*args, **kwargs):
        pytest.fail("document upload reached the filesystem")

    monkeypatch.setattr(tempfile, "TemporaryFile", forbid_disk)
    oversized = b"\xff\xd8\xff" + b"\0" * MAX_FILE_BYTES
    response = client.post(ROUTE, files={"file": ("grande.jpg", oversized)})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_input"


def test_repeated_analysis_has_the_same_result():
    first = analyze("atestado_01_pdf_nativo.pdf").json()
    second = analyze("atestado_01_pdf_nativo.pdf").json()
    first.pop("provenance")
    second.pop("provenance")
    assert first == second


def test_a_pdf_with_a_text_layer_never_calls_the_ocr():
    """A rota `direct_text` existe para não pagar OCR, e isso precisa ser contado, não suposto.

    A afirmação aparece em quatro documentos e no roteiro da demonstração. Sem contar as chamadas,
    ela é só uma frase: o pipeline poderia passar a ler tudo por OCR e nenhum teste reclamaria.
    """
    dependencies = build_dependencies("fake")
    spy = SpyOcr(dependencies.ocr)
    analyze_with_spy = build_analyzer(dependencies=replace(dependencies, ocr=spy))

    nativo = (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()
    digitalizado = (SAMPLES / "atestado_02_pdf_digitalizado.pdf").read_bytes()

    analyze_with_spy(nativo)
    assert spy.pages_read == [], "PDF com camada de texto não pode chegar ao OCR"

    analyze_with_spy(digitalizado)
    assert spy.pages_read == [1], "PDF digitalizado precisa ser lido, uma chamada por página"
