import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.aws.metrics import EmfMetrics
from adapters.clock import SystemClock
from adapters.fakes.clock import FixedClock
from adapters.fakes.metrics import InMemoryMetrics
from entrypoints import bootstrap
from entrypoints.bootstrap import (
    AWS,
    FAKE,
    GUARDRAIL_VARIABLE,
    KENDRA_INDEX_VARIABLE,
    PROFILE_VARIABLE,
    MissingConfiguration,
    UnknownProfile,
    build_analyzer,
    build_clock,
    build_dependencies,
    build_metrics,
    current_profile,
)

SRC = Path(__file__).resolve().parents[2] / "src"
SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def test_the_default_profile_is_the_one_that_costs_nothing() -> None:
    assert current_profile({}) == FAKE


@pytest.mark.parametrize("raw", ["aws", "AWS", " aws "])
def test_the_profile_is_read_from_the_environment(raw: str) -> None:
    assert current_profile({PROFILE_VARIABLE: raw}) == AWS


@pytest.mark.parametrize("raw", ["prod", "fak", "", "local"])
def test_an_unknown_profile_stops_the_process_instead_of_guessing(raw: str) -> None:
    with pytest.raises(UnknownProfile, match="is not a profile"):
        current_profile({PROFILE_VARIABLE: raw})


@pytest.mark.parametrize(
    ("profile", "expected"),
    [(FAKE, InMemoryMetrics), (AWS, EmfMetrics)],
)
def test_each_profile_wires_its_own_metrics_adapter(profile: str, expected: type) -> None:
    assert isinstance(build_metrics(profile), expected)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [(FAKE, FixedClock), (AWS, SystemClock)],
)
def test_each_profile_wires_its_own_clock(profile: str, expected: type) -> None:
    assert isinstance(build_clock(profile), expected)


def test_the_fake_clock_is_frozen_and_the_real_one_is_not() -> None:
    frozen = build_clock(FAKE)
    assert frozen.now() == frozen.now()
    assert build_clock(AWS).now() > datetime(2026, 1, 1, tzinfo=UTC)


def test_the_fake_metrics_adapter_records_what_was_emitted() -> None:
    metrics = InMemoryMetrics()
    metrics.increment("documents_analysed", {"document_type": "medical_certificate"})
    metrics.observe("analysis_latency", 1234.0, "Milliseconds", {"route": "ocr"})

    assert [emission.name for emission in metrics.emissions] == [
        "documents_analysed",
        "analysis_latency",
    ]
    assert metrics.emissions[0].value == 1.0
    assert metrics.emissions[1].unit == "Milliseconds"


def test_the_fake_profile_wires_every_reader_without_credentials() -> None:
    dependencies = build_dependencies(FAKE)
    assert dependencies.ocr is not None
    assert dependencies.llm is not None
    assert dependencies.knowledge is not None


def test_the_aws_profile_refuses_to_start_without_a_knowledge_index(monkeypatch) -> None:
    monkeypatch.delenv(KENDRA_INDEX_VARIABLE, raising=False)

    with pytest.raises(MissingConfiguration) as failure:
        build_dependencies(AWS)

    assert KENDRA_INDEX_VARIABLE in str(failure.value)


def test_the_aws_profile_builds_the_three_mandatory_readers(monkeypatch) -> None:
    monkeypatch.setenv(KENDRA_INDEX_VARIABLE, "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv(GUARDRAIL_VARIABLE, "abcd1234efgh")

    dependencies = build_dependencies(AWS)

    assert type(dependencies.ocr).__name__ == "TextractOcr"
    assert type(dependencies.llm).__name__ == "BedrockLlm"
    assert type(dependencies.knowledge).__name__ == "KendraRetriever"


def test_the_aws_profile_names_the_configured_model_and_textract_in_provenance(monkeypatch) -> None:
    monkeypatch.setenv(KENDRA_INDEX_VARIABLE, "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv(GUARDRAIL_VARIABLE, "abcd1234efgh")
    fake = build_dependencies(FAKE)
    wired = replace(
        build_dependencies(AWS),
        ocr=fake.ocr,
        llm=fake.llm,
        knowledge=fake.knowledge,
        metrics=fake.metrics,
    )
    scanned = (SAMPLES / "atestado_02_pdf_digitalizado.pdf").read_bytes()

    provenance = build_analyzer(dependencies=wired)(scanned).provenance

    configured = json.loads(bootstrap.BEDROCK_CONFIG.read_text(encoding="utf-8"))["model_id"]
    assert provenance["model_id"] == configured
    assert provenance["ocr_engine"] == "amazon-textract/detect-document-text"


def test_building_an_unknown_profile_fails_before_touching_any_adapter() -> None:
    with pytest.raises(UnknownProfile):
        build_dependencies("prod")


def test_bootstrap_is_the_only_module_that_reads_dis_profile() -> None:
    readers = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if PROFILE_VARIABLE in path.read_text(encoding="utf-8")
    )
    assert readers == ["entrypoints/bootstrap.py"]


def test_the_dependencies_set_has_no_storage_port() -> None:
    fields = set(bootstrap.Dependencies.__dataclass_fields__)
    assert fields == {
        "ocr",
        "llm",
        "knowledge",
        "metrics",
        "clock",
        "catalog",
        "prompt_version",
        "model_id",
        "ocr_engine",
    }
