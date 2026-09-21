"""Edge representation of the published contract.

These derive from `contracts/v1/analysis_result.schema.json`, never the other way round: the
contract is written first and a test proves a response still validates against it. `extra="forbid"`
mirrors `additionalProperties: false`.
"""

from typing import Literal

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from usecases.analyze import Analysis

CapabilityState = Literal["available", "degraded", "unavailable"]
FieldReason = Literal[
    "confidence_below_threshold", "invalid_evidence", "absent_from_document", "validation_failed"
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    text: str
    page: int = Field(ge=1)


class ExtractedField(Strict):
    value: object | None
    confidence: float = Field(ge=0, le=1)
    abstained: bool
    reason: FieldReason | None = None
    evidence: Evidence | None = None


class DocumentType(Strict):
    value: Literal["medical_certificate", "medical_assessment_result"]
    confidence: float = Field(ge=0, le=1)


class Validation(Strict):
    rule: str
    status: Literal["passed", "failed", "skipped"]
    detail: str | None = None


class KnowledgeReference(Strict):
    source: str
    version: str
    excerpt: str
    uri: str | None = None


class Review(Strict):
    required: bool
    reasons: list[str]


class Capabilities(Strict):
    ocr: CapabilityState
    extraction: CapabilityState
    knowledge_enrichment: CapabilityState


class Provenance(Strict):
    model_id: str
    prompt_version: str
    ocr_engine: str
    reference_tables_version: str
    analysed_at: str


class AnalysisResult(Strict):
    schema_version: Literal["1.1.0"] = "1.1.0"
    file_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    document_type: DocumentType
    fields: dict[str, ExtractedField]
    validations: list[Validation]
    knowledge: list[KnowledgeReference] | None = None
    review: Review
    capabilities: Capabilities
    provenance: Provenance


class DocumentUpload(Strict):
    file: UploadFile


def from_analysis(analysis: Analysis) -> AnalysisResult:
    return AnalysisResult.model_validate(
        {
            "file_sha256": analysis.file_sha256,
            "document_type": {
                "value": analysis.document_type.value,
                "confidence": analysis.classification_confidence,
            },
            "fields": {
                item.name: {
                    "value": item.value,
                    "confidence": item.confidence.value,
                    "abstained": item.abstained,
                    "reason": item.reason,
                    "evidence": {"text": item.evidence_text, "page": item.evidence_page}
                    if item.evidence_text
                    else None,
                }
                for item in analysis.fields
            },
            "validations": [
                {
                    "rule": rule.rule,
                    "status": "passed" if rule.passed else "failed",
                    "detail": rule.detail,
                }
                for rule in analysis.validations
            ],
            "knowledge": [
                {
                    "source": item.source,
                    "version": item.version,
                    "excerpt": item.excerpt,
                    "uri": item.uri,
                }
                for item in analysis.knowledge
            ],
            "review": {"required": analysis.review.required, "reasons": analysis.review.reasons},
            "capabilities": analysis.capabilities,
            "provenance": analysis.provenance,
        }
    )
