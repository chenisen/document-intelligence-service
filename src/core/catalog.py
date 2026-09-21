"""Which fields belong to which document type, and the tables the rules read.

Spec 0003, rule 1. This module holds the *shape* of that knowledge, never the knowledge itself: the
values arrive from configuration, loaded at the edge. A new document type is a new entry in that
configuration plus, at most, the rules that are specific to it. No layer changes and no release.

The split this file exists to make explicit: the rule is code, the table is content. `end >= start`
is a rule and lives here; which CID codes exist, which words mean granted and how a protocol number
is spelled are content, and they live in the catalogue. Reasoning about the document is neither: it
is the prompt, which is Bedrock configuration, and the internal norm, which is the Kendra index.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.document import DocumentType


@dataclass(frozen=True)
class DocumentTypeSpec:
    """One document type as configured: its fields, which of them are critical, and its tables."""

    fields: tuple[str, ...]
    # Getting these wrong does not lose a field: it sends the decision to the wrong place. Here
    # precision beats recall, and abstaining is the safe answer.
    critical: frozenset[str]
    # Terms that start the search for the applicable internal norm. The document adds to them.
    knowledge_terms: tuple[str, ...] = ()
    # Controlled vocabulary, written as it appears on the page, mapped to the contract value.
    outcomes: Mapping[str, str] = field(default_factory=dict)
    # Which outcome means nothing was granted. That no period accompanies it is a rule, so it is
    # code; which value triggers it is content, and naming it keeps the rule free of any language.
    denied_outcome: str | None = None
    protocol_pattern: str | None = None


@dataclass(frozen=True)
class Catalog:
    """Every configured document type, plus the reference tables shared between them."""

    types: Mapping[DocumentType, DocumentTypeSpec]
    cid_codes: frozenset[str]
    reference_tables_version: str
