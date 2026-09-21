"""The use case. It reads a document and describes it; it decides nothing about the business.

Specs 0001 to 0004 meet here. Every step is a port or a pure domain function, which is why this file
has no `boto3`, no HTTP and no environment variable.
"""

import hashlib
from dataclasses import dataclass

from core.analysis import ExtractedField, KnowledgeReference, TokenUsage
from core.catalog import Catalog, DocumentTypeSpec
from core.document import DocumentType, NormalizedDocument, Page, ReadingRoute
from core.policy import Decided, decide
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


def query_terms(spec: DocumentTypeSpec, values: dict[str, object]) -> list[str]:
    """What to ask the knowledge index: the configured terms plus the signal this document carries.

    A leave of more than fifteen days and a denied outcome reach different norms, and the caller
    never has to know that: it is the index that holds the rule.
    """
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
    fields: list[Decided]
    validations: list[Validation]
    knowledge: list[KnowledgeReference]
    review: Review
    capabilities: dict[str, str]
    provenance: dict[str, str]
    route: ReadingRoute
    # What the model calls consumed. The evaluation prices it; the contract never carries it.
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

        source_text, ocr_confidence, route, pages_read = self._read(
            document.route, pages, direct_text
        )

        classification = self._llm.classify(pages)
        supported = self._catalog.types
        if classification.document_type is None or classification.document_type not in supported:
            self._metrics.increment("documents_refused", {"reason": "unsupported_type"})
            raise ServiceError(
                ErrorCode.UNSUPPORTED_DOCUMENT_TYPE,
                "the document is not one of the supported types",
            )

        document_type = classification.document_type
        spec = self._catalog.types[document_type]

        # Guardrail acionado não é falha da peça: é a política funcionando. O caso vai para uma
        # pessoa, com motivo estável, e o conteúdo bloqueado não volta para o consumidor. Deixar a
        # exceção subir transformaria isso num erro genérico e perderia a informação.
        guardrail_triggered = False
        try:
            extraction = self._llm.extract(pages, document_type, self._prompt_version)
        except GuardrailTriggered as blocked:
            self._metrics.increment("guardrail_triggered", {"topic": blocked.topic})
            return self._blocked_by_guardrail(
                content, document_type, classification.confidence.value, classification.usage
            )
        if extraction.document_type is not document_type:
            raise ServiceError(ErrorCode.UPSTREAM_UNAVAILABLE, "invalid extraction response")
        returned = {item.name: item for item in extraction.fields}
        candidates = [
            returned.get(name, ExtractedField(name, None, Confidence(1.0), None))
            for name in spec.fields
        ]
        raw = {item.name: item.value for item in candidates}
        validations = validate(spec, self._catalog, raw, self._clock.now().date())
        invalid = failed_fields(validations)

        fields = [
            decide(
                item,
                spec,
                source_text,
                ocr_confidence.get(item.evidence.page, 0.0) if item.evidence else 0.0,
                item.name not in invalid,
            )
            for item in candidates
        ]

        knowledge, capabilities = self._enrich(spec, raw)
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
            provenance=self._provenance(route),
            route=route,
            pages_read=pages_read,
            model_usage=TokenUsage(
                classification.usage.input_tokens + extraction.usage.input_tokens,
                classification.usage.output_tokens + extraction.usage.output_tokens,
            ),
        )

    def _blocked_by_guardrail(
        self,
        content: bytes,
        document_type: DocumentType,
        classification_confidence: float,
        usage: TokenUsage,
    ) -> "Analysis":
        """Resposta de análise bloqueada: sem campo nenhum, e dizendo por quê.

        Nenhum valor é devolvido porque nenhum foi produzido — a saída do modelo foi bloqueada antes
        de virar resposta. O contrato aguenta `fields` vazio de propósito, e a alternativa seria
        inventar valor ou devolver erro genérico. As duas são piores.
        """
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
            provenance=self._provenance(ReadingRoute.MULTIMODAL),
            route=ReadingRoute.MULTIMODAL,
            model_usage=usage,
        )

    def _provenance(self, route: ReadingRoute) -> dict[str, str]:
        return {
            "model_id": self._model_id,
            "prompt_version": self._prompt_version,
            "ocr_engine": "none/direct-text"
            if route is ReadingRoute.DIRECT_TEXT
            else self._ocr_engine,
            "reference_tables_version": self._catalog.reference_tables_version,
            "analysed_at": self._clock.now().isoformat().replace("+00:00", "Z"),
        }

    def _read(
        self, route: ReadingRoute, pages: list[Page], direct_text: list[str]
    ) -> tuple[dict[int, str], dict[int, float], ReadingRoute, int]:
        """A PDF with a text layer is never sent to OCR: it is already text, and OCR costs."""
        if route is ReadingRoute.DIRECT_TEXT:
            return (
                dict(enumerate(direct_text, 1)),
                {page.number: 100.0 for page in pages},
                route,
                0,
            )

        recognised = [self._ocr.read(page) for page in pages]
        confidence = min((page.confidence for page in recognised), default=0.0)
        rerouted = reroute_after_ocr(route, confidence)
        if rerouted is not route:
            self._metrics.increment("pages_rerouted_to_multimodal", {"from": route.value})
        return (
            {page.number: page.text for page in recognised},
            {page.number: page.confidence for page in recognised},
            rerouted,
            len(recognised),
        )

    def _enrich(
        self, spec: DocumentTypeSpec, values: dict[str, object]
    ) -> tuple[list[KnowledgeReference], dict[str, str]]:
        """Enrichment failing degrades the answer; it does not fail it.

        The query starts from the configured terms and is completed by what the document says, so
        the norm that comes back is the one that applies to *this* document. Which norms exist and
        how they are ranked is the index, not this code.
        """
        try:
            found = list(self._knowledge.retrieve(" ".join(query_terms(spec, values))))
        except Exception:
            self._metrics.increment("knowledge_unavailable", {})
            return [], {"knowledge_enrichment": "unavailable"}
        return found, {"knowledge_enrichment": "available" if found else "degraded"}
