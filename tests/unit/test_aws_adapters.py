"""The three adapters the case makes mandatory, against recorded API shapes.

`botocore.Stubber` validates the request against the service model before answering: a parameter
that does not exist, or a required one that is missing, fails here rather than in an account. That
is what these prove. What they do not prove is permission, latency, cost or extraction quality —
only a real account proves those, and saying so is part of the delivery.
"""

import json
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber

from adapters.aws import clients
from adapters.aws.bedrock import BedrockLlm, GuardrailTriggered
from adapters.aws.kendra import KendraRetriever
from adapters.aws.textract import TextractOcr
from adapters.catalog import load_catalog
from core.analysis import TokenUsage
from core.document import DocumentType, Page

ROOT = Path(__file__).resolve().parents[2]
REGION = "us-east-1"
INDEX_ID = "11111111-2222-3333-4444-555555555555"  # Kendra requires a real index id shape.
PAGE = Page(number=1, image=b"\xff\xd8\xff-jpeg-bytes", width=1000, height=1400)
CATALOG = load_catalog()
CONFIG = json.loads((ROOT / "config" / "bedrock.json").read_text(encoding="utf-8"))


@pytest.fixture
def textract():
    client = boto3.client("textract", region_name=REGION)
    with Stubber(client) as stubber:
        yield client, stubber


@pytest.fixture
def bedrock():
    client = boto3.client("bedrock-runtime", region_name=REGION)
    with Stubber(client) as stubber:
        yield client, stubber


@pytest.fixture
def kendra():
    client = boto3.client("kendra", region_name=REGION)
    with Stubber(client) as stubber:
        yield client, stubber


def tool_use(name: str, payload: dict) -> dict:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "tu-1", "name": name, "input": payload}}],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1000, "outputTokens": 100, "totalTokens": 1100},
        "metrics": {"latencyMs": 900},
    }


def test_textract_reads_one_page_per_call_and_keeps_the_worst_confidence(textract):
    client, stubber = textract
    stubber.add_response(
        "detect_document_text",
        {
            "Blocks": [
                {"BlockType": "LINE", "Text": "ATESTADO MEDICO", "Confidence": 99.2},
                {"BlockType": "LINE", "Text": "CID-10: M54.5", "Confidence": 81.4},
                {"BlockType": "WORD", "Text": "M54.5", "Confidence": 12.0},
            ]
        },
        {"Document": {"Bytes": PAGE.image}},
    )

    result = TextractOcr(client).read(PAGE)

    assert result.number == 1
    assert result.text == "ATESTADO MEDICO\nCID-10: M54.5"
    # The lowest line, not the average: one illegible line is what reroutes the page.
    assert result.confidence == 81.4
    stubber.assert_no_pending_responses()


def test_a_throttled_textract_surfaces_as_the_error_it_is(textract):
    client, stubber = textract
    stubber.add_client_error("detect_document_text", "ThrottlingException", http_status_code=400)

    with pytest.raises(ClientError):
        TextractOcr(client).read(PAGE)


def test_bedrock_classifies_through_a_tool_schema_that_only_allows_known_types(bedrock):
    client, stubber = bedrock
    stubber.add_response(
        "converse",
        tool_use(
            "record_document_type", {"document_type": "medical_certificate", "confidence": 0.97}
        ),
        {
            "modelId": CONFIG["model_id"],
            "system": ANY,
            "messages": ANY,
            "toolConfig": ANY,
            "inferenceConfig": ANY,
        },
    )

    result = BedrockLlm(CONFIG, CATALOG, client).classify([PAGE])

    assert result.document_type is DocumentType.MEDICAL_CERTIFICATE
    assert result.confidence.value == 0.97


def test_bedrock_reports_the_tokens_the_provider_counted(bedrock):
    client, stubber = bedrock
    stubber.add_response(
        "converse",
        tool_use(
            "record_document_type", {"document_type": "medical_certificate", "confidence": 0.97}
        ),
    )
    stubber.add_response("converse", tool_use("record_fields", {}))
    llm = BedrockLlm(CONFIG, CATALOG, client)

    classification = llm.classify([PAGE])
    extraction = llm.extract([PAGE], DocumentType.MEDICAL_CERTIFICATE, "v1")

    assert classification.usage == TokenUsage(input_tokens=1000, output_tokens=100)
    assert extraction.usage == TokenUsage(input_tokens=1000, output_tokens=100)


def test_bedrock_returns_no_type_when_the_document_is_outside_the_catalogue(bedrock):
    client, stubber = bedrock
    stubber.add_response(
        "converse", tool_use("record_document_type", {"document_type": None, "confidence": 0.91})
    )

    result = BedrockLlm(CONFIG, CATALOG, client).classify([PAGE])

    assert result.document_type is None


def test_the_tool_schema_offers_exactly_the_configured_types(bedrock):
    """The catalogue builds the schema, so a type the service does not support cannot come back."""
    client, stubber = bedrock
    captured: dict = {}
    stubber.add_response(
        "converse", tool_use("record_document_type", {"document_type": None, "confidence": 0.5})
    )
    original = client.converse
    client.converse = lambda **kwargs: (captured.update(kwargs), original(**kwargs))[1]

    BedrockLlm(CONFIG, CATALOG, client).classify([PAGE])

    schema = captured["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert schema["properties"]["document_type"]["enum"] == [
        "medical_assessment_result",
        "medical_certificate",
        None,
    ]
    assert captured["toolConfig"]["toolChoice"] == {"tool": {"name": "record_document_type"}}


def test_bedrock_extraction_carries_the_excerpt_and_the_page_of_every_value(bedrock):
    client, stubber = bedrock
    fields = {
        name: {"value": None, "confidence": 0.1}
        for name in CATALOG.types[DocumentType.MEDICAL_CERTIFICATE].fields
    }
    fields["leave_period"] = {
        "value": {"start": "2026-09-14", "end": "2026-09-16", "days": 3},
        "confidence": 0.96,
        "evidence": {"text": "Afastamento de 14/09/2026 a 16/09/2026", "page": 1},
    }
    stubber.add_response("converse", tool_use("record_fields", fields))

    result = BedrockLlm(CONFIG, CATALOG, client).extract(
        [PAGE], DocumentType.MEDICAL_CERTIFICATE, "v1"
    )

    period = next(item for item in result.fields if item.name == "leave_period")
    assert period.evidence is not None
    assert period.evidence.page == 1
    assert period.confidence.value == 0.96
    # Every configured field comes back, present or absent: the answer is not a partial map.
    assert {item.name for item in result.fields} == set(
        CATALOG.types[DocumentType.MEDICAL_CERTIFICATE].fields
    )


def test_a_triggered_guardrail_does_not_return_the_blocked_content(bedrock):
    client, stubber = bedrock
    stubber.add_response(
        "converse",
        {
            "output": {"message": {"role": "assistant", "content": [{"text": "CID F32"}]}},
            "stopReason": "guardrail_intervened",
            "usage": {"inputTokens": 10, "outputTokens": 0, "totalTokens": 10},
            "metrics": {"latencyMs": 40},
        },
    )

    with pytest.raises(GuardrailTriggered) as raised:
        BedrockLlm(CONFIG, CATALOG, client).classify([PAGE])

    # The error names the guardrail, never what the model was about to say.
    assert "CID" not in str(raised.value)


class SpyConverse:
    """Records the request instead of answering a canned one: what matters here is what was sent."""

    def __init__(self) -> None:
        self.sent: dict = {}

    def converse(self, **request):
        self.sent = request
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": "irrelevant"}]}},
            "stopReason": "guardrail_intervened",
        }


def test_the_configured_guardrail_reaches_every_model_call() -> None:
    """The identifier comes from the deployment, the version from configuration, and a call that
    carries neither is a call no policy reviewed."""
    spy = SpyConverse()
    configured = {**CONFIG, "guardrail": {**CONFIG["guardrail"], "identifier": "abcd1234efgh"}}

    with pytest.raises(GuardrailTriggered):
        BedrockLlm(configured, CATALOG, spy).classify([PAGE])

    assert spy.sent["guardrailConfig"] == {
        "guardrailIdentifier": "abcd1234efgh",
        "guardrailVersion": CONFIG["guardrail"]["version"],
    }


def test_without_an_identifier_no_policy_is_claimed() -> None:
    """The `fake` profile has no guardrail, and the call must then carry no `guardrailConfig` at
    all: sending an empty one would be claiming a policy that is not there."""
    spy = SpyConverse()

    with pytest.raises(GuardrailTriggered):
        BedrockLlm(CONFIG, CATALOG, spy).classify([PAGE])

    assert "guardrailConfig" not in spy.sent


def test_kendra_returns_the_passage_with_its_source_and_version(kendra):
    client, stubber = kendra
    stubber.add_response(
        "retrieve",
        {
            "ResultItems": [
                {
                    "Id": "r-1",
                    "DocumentId": "ni-rh-014",
                    "DocumentTitle": "Norma interna de afastamento, NI-RH-014",
                    "DocumentURI": "https://intranet.invalido/ni-rh-014",
                    "Content": "Afastamento superior a 15 dias segue para o INSS.",
                    "DocumentAttributes": [
                        {"Key": "_version", "Value": {"StringValue": "2026-04"}}
                    ],
                }
            ]
        },
        {"IndexId": INDEX_ID, "QueryText": "atestado afastamento 20", "PageSize": 3},
    )

    found = KendraRetriever(INDEX_ID, client=client).retrieve("atestado afastamento 20")

    assert len(found) == 1
    assert found[0].source == "Norma interna de afastamento, NI-RH-014"
    assert found[0].version == "2026-04"
    assert found[0].excerpt.startswith("Afastamento superior")


def test_the_retrieval_asks_the_index_to_exclude_a_revoked_norm(kendra):
    """The configured filter has to reach the call, or it is decoration.

    Taking the document out of the index on revocation is right and is not enough: between the
    revocation and the next sync there is a window, and it is in that window that a superseded
    norm would ground a decision about someone's leave. The Stubber rejects the request if the
    filter does not match, which is what makes this a check and not a reading of the file.
    """
    client, stubber = kendra
    configured = json.loads((ROOT / "config" / "kendra.json").read_text(encoding="utf-8"))
    attribute_filter = configured["retrieve"]["AttributeFilter"]
    stubber.add_response(
        "retrieve",
        {"ResultItems": []},
        {
            "IndexId": INDEX_ID,
            "QueryText": "atestado",
            "PageSize": 3,
            "AttributeFilter": attribute_filter,
        },
    )

    KendraRetriever(INDEX_ID, attribute_filter, client=client).retrieve("atestado")

    stubber.assert_no_pending_responses()
    assert attribute_filter["AndAllFilters"][0]["EqualsTo"]["Value"]["StringValue"] == "vigente"


def test_a_norm_without_a_recorded_version_is_reported_as_unknown(kendra):
    client, stubber = kendra
    stubber.add_response(
        "retrieve",
        {"ResultItems": [{"Id": "r-1", "DocumentId": "sem-versao", "Content": "texto"}]},
        {"IndexId": INDEX_ID, "QueryText": "qualquer", "PageSize": 3},
    )

    found = KendraRetriever(INDEX_ID, client=client).retrieve("qualquer")

    # Reported, never invented: provenance says which version answered, and here nobody knows.
    assert found[0].version == "unknown"


# --- Budgets -------------------------------------------------------------
# The default boto3 timeout is a minute per attempt. In a synchronous pipeline behind a declared p95
# that is a hang, not a timeout, so every dependency gets a number that somebody chose.


@pytest.mark.parametrize("service", sorted(clients.BUDGETS))
def test_every_dependency_declares_a_timeout_and_a_retry_policy(service: str) -> None:
    config = clients.build_client(service).meta.config

    budget = clients.BUDGETS[service]
    assert config.connect_timeout == budget.connect
    assert config.read_timeout == budget.read
    # Adaptive backs off when the service is already rate limiting, instead of adding load to a
    # dependency that is asking for less.
    assert config.retries["mode"] == "adaptive"
    assert config.retries["total_max_attempts"] == budget.total_attempts


@pytest.mark.parametrize("service", sorted(clients.BUDGETS))
def test_no_single_dependency_can_hang_past_the_declared_p95(service: str) -> None:
    """The contract declares p95 of 25 s, and a timeout nobody chose is a hang, not a timeout.

    The rule is per dependency, not on the sum: the sum of every attempt of everything timing out is
    past any percentile, and p95 is a percentile, not a ceiling on every request.
    """
    assert clients.BUDGETS[service].worst_case < clients.LATENCY_TARGET_P95


def test_the_dependency_that_only_degrades_is_the_one_that_waits_least() -> None:
    """Kendra failing loses the norm reference; Bedrock failing loses the answer."""
    assert clients.BUDGETS["kendra"].read < clients.BUDGETS["textract"].read
    assert clients.BUDGETS["textract"].read < clients.BUDGETS["bedrock-runtime"].read
