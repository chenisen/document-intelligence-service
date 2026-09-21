import json
from pathlib import Path

from core.catalog import Catalog, DocumentTypeSpec
from core.document import DocumentType

CATALOG = Path(__file__).resolve().parents[2] / "config" / "catalog.json"


def load_catalog(path: Path = CATALOG) -> Catalog:
    catalog_config = json.loads(path.read_text(encoding="utf-8"))
    return Catalog(
        types={
            DocumentType(name): DocumentTypeSpec(
                fields=tuple(type_config["fields"]),
                critical=frozenset(type_config.get("critical", ())),
                knowledge_terms=tuple(type_config.get("knowledge_terms", ())),
                outcomes=dict(type_config.get("outcomes", {})),
                denied_outcome=type_config.get("denied_outcome"),
                protocol_pattern=type_config.get("protocol_pattern"),
            )
            for name, type_config in catalog_config["document_types"].items()
        },
        cid_codes=frozenset(catalog_config["cid_codes"]),
        reference_tables_version=catalog_config["reference_tables_version"],
    )
