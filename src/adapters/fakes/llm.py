from collections.abc import Sequence

from adapters.fakes.reference import (
    CONFIDENCE_WITH_EVIDENCE,
    CONFIDENCE_WITHOUT_EVIDENCE,
    evidence_search_term,
    reference_case_for_document,
    to_contract_value,
)
from core.analysis import Classification, ExtractedField, Extraction
from core.document import DocumentType, Page
from core.values import Confidence, Evidence
from usecases.ports import LlmPort


def _find_field_evidence(page_texts: Sequence[str], search_term: str | None) -> Evidence | None:
    if not search_term:
        return None
    for page_number, page_text in enumerate(page_texts, 1):
        for line in page_text.splitlines():
            if search_term in line:
                return Evidence(text=line.strip(), page=page_number)
    return None


class StubLlm(LlmPort):
    def classify(self, pages: Sequence[Page]) -> Classification:
        reference_case = reference_case_for_document(pages)
        return Classification(
            document_type=reference_case.document_type,
            confidence=Confidence(0.97 if reference_case.document_type else 0.93),
        )

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        reference_case = reference_case_for_document(pages)
        fields = []
        for field_name, value in reference_case.fields.items():
            evidence = _find_field_evidence(reference_case.page_texts, evidence_search_term(value))
            fields.append(
                ExtractedField(
                    name=field_name,
                    value=to_contract_value(field_name, value),
                    confidence=Confidence(
                        CONFIDENCE_WITH_EVIDENCE if evidence else CONFIDENCE_WITHOUT_EVIDENCE
                    ),
                    evidence=evidence,
                )
            )
        return Extraction(document_type=document_type, fields=tuple(fields))
