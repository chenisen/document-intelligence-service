import ast
import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adapters.fakes.knowledge import FailingKnowledgeRetriever
from entrypoints.bootstrap import build_analyzer, build_dependencies
from entrypoints.http.app import app, get_dependencies

ROOT = Path(__file__).resolve().parents[2]
CONTENT = (ROOT / "samples/atestado_01_pdf_nativo.pdf").read_bytes()


def test_analysis_emits_only_allowed_audit_metadata(caplog):
    with caplog.at_level(logging.INFO):
        response = TestClient(app).post(
            "/v1/documents:analyze",
            files={"file": ("private.pdf", CONTENT)},
            headers={"x-caller": "untrusted-person-name"},
        )
    assert response.status_code == 200
    records = [record for record in caplog.records if record.msg == "document_analysis"]
    assert len(records) == 1
    record = records[0]
    assert record.file_sha256 == hashlib.sha256(CONTENT).hexdigest()
    assert record.caller == "local"
    assert record.route == "direct_text"
    assert record.outcome == "success"
    assert record.confidence_by_field["leave_period"] >= 0.9
    assert record.model_id == "stub/reference-set"
    from entrypoints.bootstrap import BEDROCK_CONFIG

    assert record.prompt_version == json.loads(BEDROCK_CONFIG.read_text())["prompt_version"]
    serialized = json.dumps(record.__dict__, default=str)
    for forbidden in (
        "Ana Beatriz",
        "000.000.000-00",
        "M54.5",
        "private.pdf",
        "untrusted-person-name",
        "Helena Vasconcelos",
    ):
        assert forbidden not in serialized


def test_failures_do_not_leak_document_content(monkeypatch, caplog):
    dependencies = build_dependencies("fake")

    def fail(pages):
        raise RuntimeError("private patient 000.000.000-00 M54.5")

    monkeypatch.setattr(dependencies.llm, "classify", fail)
    app.dependency_overrides[get_dependencies] = lambda: dependencies
    try:
        with caplog.at_level(logging.INFO):
            response = TestClient(app, raise_server_exceptions=False).post(
                "/v1/documents:analyze",
                files={"file": ("x.pdf", CONTENT)},
            )
        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"
        assert "private patient" not in response.text + caplog.text
        records = [record for record in caplog.records if record.msg == "document_analysis"]
        assert len(records) == 1
        assert records[0].outcome == "internal_error"
        assert records[0].exc_info is None
    finally:
        app.dependency_overrides.clear()


def test_a_failing_knowledge_adapter_degrades_instead_of_failing():
    dependencies = replace(build_dependencies("fake"), knowledge=FailingKnowledgeRetriever())
    result = build_analyzer(dependencies=dependencies)(CONTENT)
    assert result.capabilities["knowledge_enrichment"] == "unavailable"
    assert result.fields[0].value == "Ana Beatriz Marques da Silva"


def test_service_has_no_document_writing_adapter():
    forbidden = {"write_text", "write_bytes", "save", "put_object", "put_item", "upload_file"}
    for path in (ROOT / "src/adapters").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and (path.name, node.func.attr) != ("documents.py", "save")
            ):
                assert node.func.attr not in forbidden, f"writing adapter: {path}:{node.lineno}"
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
                and len(node.args) > 1
            ):
                assert isinstance(node.args[1], ast.Constant)
                assert node.args[1].value in ("r", "rb")


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError("sensitive"), "upstream_timeout"),
        (ConnectionError("sensitive"), "upstream_unavailable"),
    ],
)
def test_upstream_errors_are_mapped_without_their_messages(monkeypatch, error, code):
    dependencies = build_dependencies("fake")

    def fail(pages):
        raise error

    monkeypatch.setattr(dependencies.llm, "classify", fail)
    app.dependency_overrides[get_dependencies] = lambda: dependencies
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/v1/documents:analyze",
            files={"file": ("x.pdf", CONTENT)},
        )
        assert response.json()["code"] == code
        assert "sensitive" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_a_revoked_norm_is_never_cited() -> None:
    from adapters.fakes.knowledge import CORPUS, FakeKnowledgeRetriever

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["normas"]
    revoked = [norm for norm in corpus if norm.get("status") == "revogada"]
    assert revoked, "o corpus precisa manter uma norma revogada para esta regra ser testável"

    found = FakeKnowledgeRetriever().retrieve("atestado afastamento prontuario")

    assert found, "os termos precisam alcançar a norma vigente equivalente"
    assert {norm["source"] for norm in revoked}.isdisjoint({item.source for item in found})
