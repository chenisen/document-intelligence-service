from collections.abc import Sequence
from typing import Any

from adapters.aws.clients import build_client
from core.analysis import Classification, ExtractedField, Extraction, TokenUsage
from core.catalog import Catalog
from core.document import DocumentType, Page
from core.values import Confidence, Evidence
from usecases.ports import GuardrailTriggered, LlmPort

CLASSIFY_TOOL = "record_document_type"
EXTRACT_TOOL = "record_fields"
GUARDRAIL_INTERVENED = "guardrail_intervened"


def _field_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": {
                "description": "the value exactly as written in the document, or null if absent"
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "literal excerpt from the page"},
                    "page": {"type": "integer", "minimum": 1},
                },
                "required": ["text", "page"],
            },
        },
        "required": ["value", "confidence"],
    }


class BedrockLlm(LlmPort):
    def __init__(self, config: dict[str, Any], catalog: Catalog, client: Any | None = None) -> None:
        self._config = config
        self._catalog = catalog
        self._client = client if client is not None else build_client("bedrock-runtime")

    @property
    def model_id(self) -> str:
        return str(self._config["model_id"])

    def classify(self, pages: Sequence[Page]) -> Classification:
        names = sorted(document_type.value for document_type in self._catalog.types)
        tool_payload, usage = self._invoke_structured_model(
            pages,
            self._config["classify_prompt"],
            CLASSIFY_TOOL,
            {
                "type": "object",
                "properties": {
                    "document_type": {
                        "type": ["string", "null"],
                        "enum": [*names, None],
                        "description": "null when the document is none of these",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["document_type", "confidence"],
            },
        )
        value = tool_payload.get("document_type")
        return Classification(
            document_type=DocumentType(value) if value else None,
            confidence=Confidence(float(tool_payload["confidence"])),
            usage=usage,
        )

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        names = self._catalog.types[document_type].fields
        tool_payload, usage = self._invoke_structured_model(
            pages,
            f"{self._config['extract_prompt']}\n\nDocumento: {document_type.value}.",
            EXTRACT_TOOL,
            {
                "type": "object",
                "properties": {name: _field_schema() for name in names},
                "required": list(names),
            },
        )
        return Extraction(
            document_type=document_type,
            fields=tuple(
                ExtractedField(
                    name=name,
                    value=field.get("value"),
                    confidence=Confidence(float(field.get("confidence", 0.0))),
                    evidence=(
                        Evidence(text=field["evidence"]["text"], page=field["evidence"]["page"])
                        if field.get("evidence")
                        else None
                    ),
                )
                for name, field in ((name, tool_payload.get(name) or {}) for name in names)
            ),
            usage=usage,
        )

    def _invoke_structured_model(
        self, pages: Sequence[Page], prompt: str, tool_name: str, output_schema: dict[str, Any]
    ) -> tuple[dict[str, Any], TokenUsage]:
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": prompt}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": {"format": "jpeg", "source": {"bytes": page.image}}}
                        for page in pages
                    ],
                }
            ],
            "toolConfig": {
                "tools": [
                    {"toolSpec": {"name": tool_name, "inputSchema": {"json": output_schema}}}
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
            "inferenceConfig": {"maxTokens": self._config["max_tokens"], "temperature": 0},
        }
        guardrail = self._config.get("guardrail") or {}
        if guardrail.get("identifier"):
            request["guardrailConfig"] = {
                "guardrailIdentifier": guardrail["identifier"],
                "guardrailVersion": str(guardrail["version"]),
            }

        response = self._client.converse(**request)
        if response.get("stopReason") == GUARDRAIL_INTERVENED:
            raise GuardrailTriggered(response.get("stopReason", GUARDRAIL_INTERVENED))

        usage = TokenUsage(response["usage"]["inputTokens"], response["usage"]["outputTokens"])
        for block in response["output"]["message"]["content"]:
            if "toolUse" in block and block["toolUse"]["name"] == tool_name:
                return dict(block["toolUse"]["input"]), usage
        raise ValueError(f"the model answered without calling {tool_name}")
