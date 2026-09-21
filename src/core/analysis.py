"""What the reading of a document produces, before it is turned into the published contract."""

from dataclasses import dataclass

from core.document import DocumentType
from core.values import Confidence, Evidence


@dataclass(frozen=True)
class TokenUsage:
    """What model calls consumed, as the provider reported it. Evaluation data, never contract."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Classification:
    """`document_type` is None when the document is none of the supported types. The service refuses
    rather than extracting fields that the document does not have."""

    document_type: DocumentType | None
    confidence: Confidence
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True)
class ExtractedField:
    """One field as the model returned it, before the evidence check and before the thresholds.

    `value` is None for a field that is absent from the document. A field is never inferred and
    never filled by guessing.
    """

    name: str
    value: object | None
    confidence: Confidence
    evidence: Evidence | None


@dataclass(frozen=True)
class Extraction:
    document_type: DocumentType
    fields: tuple[ExtractedField, ...]
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True)
class KnowledgeReference:
    """An internal norm retrieved for this document, with where it came from and which version."""

    source: str
    version: str
    excerpt: str
    uri: str | None = None
