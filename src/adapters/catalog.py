"""Reads the document type catalogue from configuration.

It is an adapter because it touches the filesystem, and it is the only place that knows the
catalogue is a JSON file. In a deployed environment the path comes from configuration; here it
defaults to the file in the repository.
"""

import json
from pathlib import Path

from core.catalog import Catalog, DocumentTypeSpec
from core.document import DocumentType

CATALOG = Path(__file__).resolve().parents[2] / "config" / "catalog.json"


def load_catalog(path: Path = CATALOG) -> Catalog:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Catalog(
        types={
            DocumentType(name): DocumentTypeSpec(
                fields=tuple(spec["fields"]),
                critical=frozenset(spec.get("critical", ())),
                knowledge_terms=tuple(spec.get("knowledge_terms", ())),
                outcomes=dict(spec.get("outcomes", {})),
                denied_outcome=spec.get("denied_outcome"),
                protocol_pattern=spec.get("protocol_pattern"),
            )
            for name, spec in raw["document_types"].items()
        },
        cid_codes=frozenset(raw["cid_codes"]),
        reference_tables_version=raw["reference_tables_version"],
    )
