from collections.abc import Mapping
from dataclasses import dataclass, field

from core.document import DocumentType


@dataclass(frozen=True)
class DocumentTypeSpec:
    fields: tuple[str, ...]
    critical: frozenset[str]
    knowledge_terms: tuple[str, ...] = ()
    outcomes: Mapping[str, str] = field(default_factory=dict)
    denied_outcome: str | None = None
    protocol_pattern: str | None = None


@dataclass(frozen=True)
class Catalog:
    types: Mapping[DocumentType, DocumentTypeSpec]
    cid_codes: frozenset[str]
    reference_tables_version: str
