import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from adapters.documents import detect_format, read_pdf_text, render_document_pages
from core.document import DocumentType, Page, SourceFormat

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
ANSWER_KEY_PATH = SAMPLES / "answer_key.json"

CONFIDENCE_WITH_EVIDENCE = 0.96
CONFIDENCE_WITHOUT_EVIDENCE = 0.25
OCR_CONFIDENCE = 96.0

DOCUMENT_TYPE_NAMES: dict[str, str | None] = {
    "atestado_medico": "medical_certificate",
    "resultado_avaliacao_medica": "medical_assessment_result",
    "aso": None,
    "fora_do_escopo": None,
}

FIELD_NAMES = {
    "paciente_nome": "patient_name",
    "paciente_documento": "patient_document",
    "periodo_afastamento": "leave_period",
    "cid": "cid",
    "medico_nome": "doctor_name",
    "crm": "crm",
    "cnes": "cnes",
    "data_emissao": "issue_date",
    "protocolo": "protocol_number",
    "requerente_nome": "requester_name",
    "requerente_documento": "requester_document",
    "tipo_avaliacao": "assessment_type",
    "data_avaliacao": "assessment_date",
    "desfecho": "outcome",
    "periodo_concedido": "granted_period",
}

FIELD_LABELS = {
    "patient_name": "Paciente",
    "patient_document": "CPF",
    "cid": "CID-10",
    "doctor_name": "Medico",
    "cnes": "CNES",
    "issue_date": "Data de emissao",
    "protocol_number": "Protocolo",
    "requester_name": "Requerente",
    "requester_document": "CPF do requerente",
    "assessment_type": "Tipo de avaliacao",
    "assessment_date": "Data da avaliacao",
    "outcome": "Desfecho",
}

OUTCOME_VALUES = {"Deferido": "granted", "Indeferido": "denied"}


def reference_fingerprint(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def to_contract_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name in {"issue_date", "assessment_date"}:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    if name == "outcome":
        return OUTCOME_VALUES[value]
    if name == "crm":
        return {"number": value["numero"], "state": value["uf"]}
    if name in {"leave_period", "granted_period"}:
        period = {
            "start": to_contract_value("issue_date", value["inicio"]),
            "end": to_contract_value("issue_date", value["fim"]),
        }
        if "dias" in value:
            period["days"] = value["dias"]
        return period
    return value


def evidence_search_term(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("inicio", "numero"):
            if key in value:
                return str(value[key])
        return None
    return str(value)


def build_synthetic_page_text(fields: dict[str, Any]) -> str:
    lines = []
    for source_field_name, value in fields.items():
        field_name = FIELD_NAMES.get(source_field_name, source_field_name)
        search_term = evidence_search_term(value)
        if search_term is None:
            continue
        if field_name == "leave_period":
            lines.append(
                f"Afastamento de {value['inicio']} a {value['fim']}, por {value['dias']} dia(s)"
            )
        elif field_name == "granted_period":
            lines.append(f"Periodo concedido de {value['inicio']} a {value['fim']}")
        elif field_name == "crm":
            lines.append(f"CRM/{value['uf']} {value['numero']}")
        else:
            lines.append(f"{FIELD_LABELS.get(field_name, field_name)}: {search_term}")
    return "\n".join(lines)


@dataclass(frozen=True)
class ReferenceCase:
    document_type: DocumentType | None
    page_texts: tuple[str, ...]
    fields: dict[str, Any]


@lru_cache(maxsize=1)
def build_reference_index() -> tuple[
    dict[str, tuple[ReferenceCase, int]], dict[str, ReferenceCase]
]:
    cases_by_page: dict[str, tuple[ReferenceCase, int]] = {}
    cases_by_document: dict[str, ReferenceCase] = {}

    for answer_key_case in json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8")):
        content = (SAMPLES / answer_key_case["arquivo"]).read_bytes()
        pages = render_document_pages(content)

        if detect_format(content) is SourceFormat.PDF and any(read_pdf_text(content)[0]):
            page_texts = tuple(read_pdf_text(content)[1])
        else:
            page_texts = (build_synthetic_page_text(answer_key_case["campos"]),)

        reference_case = ReferenceCase(
            document_type=(
                DocumentType(DOCUMENT_TYPE_NAMES[answer_key_case["tipo_documento"]])
                if DOCUMENT_TYPE_NAMES[answer_key_case["tipo_documento"]]
                else None
            ),
            page_texts=page_texts,
            fields={
                FIELD_NAMES.get(field_name, field_name): value
                for field_name, value in answer_key_case["campos"].items()
            },
        )
        for page in pages:
            cases_by_page[reference_fingerprint(page.image)] = (reference_case, page.number)
        cases_by_document[reference_fingerprint(b"".join(page.image for page in pages))] = (
            reference_case
        )

    return cases_by_page, cases_by_document


class UnknownReferenceDocument(LookupError):
    pass


def reference_case_for_page(page: Page) -> tuple[ReferenceCase, int]:
    cases_by_page, _ = build_reference_index()
    key = reference_fingerprint(page.image)
    if key not in cases_by_page:
        raise UnknownReferenceDocument(
            f"página {key!r} não está no conjunto de referência. "
            f"O perfil `fake` só responde pelos documentos de `samples/`; rode `make fixtures`."
        )
    return cases_by_page[key]


def reference_case_for_document(pages: Sequence[Page]) -> ReferenceCase:
    _, cases_by_document = build_reference_index()
    key = reference_fingerprint(b"".join(page.image for page in pages))
    if key not in cases_by_document:
        raise UnknownReferenceDocument(
            f"documento {key!r} não está no conjunto de referência. "
            f"O perfil `fake` só responde pelos documentos de `samples/`; rode `make fixtures`."
        )
    return cases_by_document[key]
