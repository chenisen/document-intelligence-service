from dataclasses import dataclass

from core.document import DocumentType
from core.values import Confidence, Evidence


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Classification:
    document_type: DocumentType | None
    confidence: Confidence
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True)
class ExtractedField:
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
    source: str
    version: str
    excerpt: str
    uri: str | None = None
