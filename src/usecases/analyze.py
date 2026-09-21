import hashlib
from dataclasses import dataclass

from core.analysis import ExtractedField, KnowledgeReference, TokenUsage
from core.catalog import Catalog, DocumentTypeSpec
from core.document import DocumentType, NormalizedDocument, Page, ReadingRoute
from core.policy import FieldDecision, decide_field
from core.review import Review, decide_review
from core.routing import reroute_after_ocr
from core.validation import Validation, failed_fields, validate
from core.values import Confidence
from usecases.errors import ErrorCode, ServiceError
from usecases.ports import (
    Clock,
    GuardrailTriggered,
    KnowledgeRetriever,
    LlmPort,
    MetricsPort,
    OcrPort,
)


def knowledge_query_terms(spec: DocumentTypeSpec, values: dict[str, object]) -> list[str]:
    terms = list(spec.knowledge_terms)
    cid = values.get("cid")
    if isinstance(cid, str):
        terms.append(cid)
    outcome = values.get("outcome")
    if isinstance(outcome, str):
        terms.append(outcome)
    for name in ("leave_period", "granted_period"):
        period = values.get(name)
        if isinstance(period, dict) and isinstance(period.get("days"), int):
            terms.append(str(period["days"]))
    return terms


@dataclass(frozen=True)
class Analysis:
    file_sha256: str
    document_type: DocumentType
    classification_confidence: float
    fields: list[FieldDecision]
    validations: list[Validation]
    knowledge: list[KnowledgeReference]
    review: Review
    capabilities: dict[str, str]
    provenance: dict[str, str]
    route: ReadingRoute
    model_usage: TokenUsage
    pages_read: int = 0


class AnalyzeDocument:
    def __init__(
        self,
        ocr: OcrPort,
        llm: LlmPort,
        knowledge: KnowledgeRetriever,
        metrics: MetricsPort,
        clock: Clock,
        catalog: Catalog,
        model_id: str,
        ocr_engine: str,
        prompt_version: str,
    ) -> None:
        self._ocr = ocr
        self._llm = llm
        self._knowledge = knowledge
        self._metrics = metrics
        self._clock = clock
        self._catalog = catalog
        self._prompt_version = prompt_version
        self._model_id = model_id
        self._ocr_engine = ocr_engine

    def __call__(
        self,
        content: bytes,
        document: NormalizedDocument,
        pages: list[Page],
        direct_text: list[str],
    ) -> Analysis:
        if document.route is ReadingRoute.REJECT:
            raise ServiceError(
                ErrorCode.DOCUMENT_QUALITY_TOO_LOW,
                "the document is below the minimum quality for a reliable reading",
            )

        source_text_by_page, ocr_confidence_by_page, route, pages_read = self._read_source_text(
            document.route, pages, direct_text
        )

        classification = self._llm.classify(pages)
        supported_types = self._catalog.types
        if (
            classification.document_type is None
            or classification.document_type not in supported_types
        ):
            self._metrics.increment("documents_refused", {"reason": "unsupported_type"})
            raise ServiceError(
                ErrorCode.UNSUPPORTED_DOCUMENT_TYPE,
                "the document is not one of the supported types",
            )

        document_type = classification.document_type
        spec = self._catalog.types[document_type]

        guardrail_triggered = False
        try:
            extraction = self._llm.extract(pages, document_type, self._prompt_version)
        except GuardrailTriggered as blocked:
            self._metrics.increment("guardrail_triggered", {"topic": blocked.topic})
            return self._build_guardrail_blocked_analysis(
                content, document_type, classification.confidence.value, classification.usage
            )
        if extraction.document_type is not document_type:
            raise ServiceError(ErrorCode.UPSTREAM_UNAVAILABLE, "invalid extraction response")
        extracted_fields_by_name = {item.name: item for item in extraction.fields}
        candidate_fields = [
            extracted_fields_by_name.get(name, ExtractedField(name, None, Confidence(1.0), None))
            for name in spec.fields
        ]
        candidate_values = {item.name: item.value for item in candidate_fields}
        validations = validate(spec, self._catalog, candidate_values, self._clock.now().date())
        invalid_field_names = failed_fields(validations)

        fields = [
            decide_field(
                item,
                spec,
                source_text_by_page,
                ocr_confidence_by_page.get(item.evidence.page, 0.0) if item.evidence else 0.0,
                item.name not in invalid_field_names,
            )
            for item in candidate_fields
        ]

        knowledge, capabilities = self._retrieve_knowledge(spec, candidate_values)
        review = decide_review(
            spec,
            fields,
            validations,
            classification.confidence.value,
            marginal_quality=document.smallest_text_height_px <= 17,
            guardrail_triggered=guardrail_triggered,
        )

        self._metrics.increment(
            "documents_analysed",
            {"document_type": document_type.value, "review": str(review.required).lower()},
        )

        return Analysis(
            file_sha256=hashlib.sha256(content).hexdigest(),
            document_type=document_type,
            classification_confidence=classification.confidence.value,
            fields=fields,
            validations=validations,
            knowledge=knowledge,
            review=review,
            capabilities={"ocr": "available", "extraction": "available", **capabilities},
            provenance=self._build_provenance(route),
            route=route,
            pages_read=pages_read,
            model_usage=TokenUsage(
                classification.usage.input_tokens + extraction.usage.input_tokens,
                classification.usage.output_tokens + extraction.usage.output_tokens,
            ),
        )

    def _build_guardrail_blocked_analysis(
        self,
        content: bytes,
        document_type: DocumentType,
        classification_confidence: float,
        usage: TokenUsage,
    ) -> "Analysis":
        return Analysis(
            file_sha256=hashlib.sha256(content).hexdigest(),
            document_type=document_type,
            classification_confidence=classification_confidence,
            fields=[],
            validations=[],
            knowledge=[],
            review=Review(required=True, reasons=("guardrail_triggered",)),
            capabilities={
                "ocr": "available",
                "extraction": "unavailable",
                "knowledge_enrichment": "unavailable",
            },
            provenance=self._build_provenance(ReadingRoute.MULTIMODAL),
            route=ReadingRoute.MULTIMODAL,
            model_usage=usage,
        )

    def _build_provenance(self, route: ReadingRoute) -> dict[str, str]:
        return {
            "model_id": self._model_id,
            "prompt_version": self._prompt_version,
            "ocr_engine": "none/direct-text"
            if route is ReadingRoute.DIRECT_TEXT
            else self._ocr_engine,
            "reference_tables_version": self._catalog.reference_tables_version,
            "analysed_at": self._clock.now().isoformat().replace("+00:00", "Z"),
        }

    def _read_source_text(
        self, route: ReadingRoute, pages: list[Page], direct_text: list[str]
    ) -> tuple[dict[int, str], dict[int, float], ReadingRoute, int]:
        if route is ReadingRoute.DIRECT_TEXT:
            return (
                dict(enumerate(direct_text, 1)),
                {page.number: 100.0 for page in pages},
                route,
                0,
            )

        recognised_pages = [self._ocr.read(page) for page in pages]
        lowest_page_confidence = min((page.confidence for page in recognised_pages), default=0.0)
        route_after_ocr = reroute_after_ocr(route, lowest_page_confidence)
        if route_after_ocr is not route:
            self._metrics.increment("pages_rerouted_to_multimodal", {"from": route.value})
        return (
            {page.number: page.text for page in recognised_pages},
            {page.number: page.confidence for page in recognised_pages},
            route_after_ocr,
            len(recognised_pages),
        )

    def _retrieve_knowledge(
        self, spec: DocumentTypeSpec, values: dict[str, object]
    ) -> tuple[list[KnowledgeReference], dict[str, str]]:
        try:
            references = list(
                self._knowledge.retrieve(" ".join(knowledge_query_terms(spec, values)))
            )
        except Exception:
            self._metrics.increment("knowledge_unavailable", {})
            return [], {"knowledge_enrichment": "unavailable"}
        return references, {"knowledge_enrichment": "available" if references else "degraded"}
