"""The generative model, through the Bedrock `Converse` API.

This adapter is transport. It does not know what a medical certificate is and it holds no prompt:
the instruction, the model id and the guardrail come from configuration, and the output schema is
built from the catalogue. That is the whole point of the split — the reasoning about the document
lives in Bedrock configuration, evolves there, and is evaluated there, without a release here.

Two things it does insist on, because they are contract, not prompt:

* the answer comes back through a tool schema, so a field outside the format cannot be returned;
* every value carries the excerpt it came from, which `core.policy` then looks for in the
  recognised text. A field whose excerpt is not there falls, however confident the model was.
"""

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
    """One shape for every field of every type: the value, how sure, and where it came from."""
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
        answer, usage = self._converse(
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
        value = answer.get("document_type")
        return Classification(
            document_type=DocumentType(value) if value else None,
            confidence=Confidence(float(answer["confidence"])),
            usage=usage,
        )

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        names = self._catalog.types[document_type].fields
        answer, usage = self._converse(
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
                for name, field in ((name, answer.get(name) or {}) for name in names)
            ),
            usage=usage,
        )

    def _converse(
        self, pages: Sequence[Page], prompt: str, tool: str, schema: dict[str, Any]
    ) -> tuple[dict[str, Any], TokenUsage]:
        """One call, one tool, and the tool is the only way out: the answer fits the schema."""
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
                "tools": [{"toolSpec": {"name": tool, "inputSchema": {"json": schema}}}],
                "toolChoice": {"tool": {"name": tool}},
            },
            "inferenceConfig": {"maxTokens": self._config["max_tokens"], "temperature": 0},
        }
        # The identifier differs per account and arrives from the environment; the version is
        # governance and lives in the configuration file. Without an identifier no policy is sent,
        # which only the `fake` profile is allowed to do: `bootstrap` refuses it under `aws`.
        guardrail = self._config.get("guardrail") or {}
        if guardrail.get("identifier"):
            request["guardrailConfig"] = {
                "guardrailIdentifier": guardrail["identifier"],
                "guardrailVersion": str(guardrail["version"]),
            }

        response = self._client.converse(**request)
        if response.get("stopReason") == GUARDRAIL_INTERVENED:
            raise GuardrailTriggered(response.get("stopReason", GUARDRAIL_INTERVENED))

        # `usage` is a required member of the Converse response: the provider always reports it.
        usage = TokenUsage(response["usage"]["inputTokens"], response["usage"]["outputTokens"])
        for block in response["output"]["message"]["content"]:
            if "toolUse" in block and block["toolUse"]["name"] == tool:
                return dict(block["toolUse"]["input"]), usage
        raise ValueError(f"the model answered without calling {tool}")
