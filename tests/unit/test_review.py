"""RF-13: one decision for each of the seven human-review triggers."""

from dataclasses import replace
from pathlib import Path

import pytest

from core.catalog import DocumentTypeSpec
from core.policy import Decided, Reason
from core.review import decide_review
from core.validation import Validation
from core.values import Confidence

# The spec is built here instead of loaded: what these rules do must not depend on which document
# types happen to be configured. That the shipped configuration is well formed is `test_catalog.py`.
CERTIFICATE = DocumentTypeSpec(fields=("leave_period", "crm"), critical=frozenset({"leave_period"}))
ASSESSMENT = DocumentTypeSpec(fields=("outcome",), critical=frozenset({"outcome"}))

PERIOD = Decided("leave_period", {"days": 3}, Confidence(0.99), False, None, "3 dias", 1)


def test_low_field_confidence_requires_review():
    field = replace(PERIOD, name="crm", value=None, reason=Reason.CONFIDENCE_BELOW_THRESHOLD)
    review = decide_review(CERTIFICATE, [PERIOD, field], [], 0.99)
    assert review.required
    assert review.reasons == ("confidence_below_threshold:crm",)


def test_missing_critical_field_requires_review():
    field = replace(PERIOD, value=None, reason=Reason.ABSENT_FROM_DOCUMENT)
    review = decide_review(CERTIFICATE, [field], [], 0.99)
    assert review.required
    assert review.reasons == ("critical_field_missing:leave_period",)


@pytest.mark.parametrize(
    ("spec", "field"),
    [(CERTIFICATE, "leave_period"), (ASSESSMENT, "outcome")],
)
def test_omitted_critical_field_requires_review(spec, field):
    review = decide_review(spec, [], [], 0.99)
    assert review.required
    assert review.reasons == (f"critical_field_missing:{field}",)


def test_invalid_evidence_requires_review():
    field = replace(PERIOD, name="crm", value=None, reason=Reason.INVALID_EVIDENCE)
    review = decide_review(CERTIFICATE, [PERIOD, field], [], 0.99)
    assert review.required
    assert review.reasons == ("invalid_evidence:crm",)


def test_failed_validation_requires_review():
    rules = [Validation("crm_format", False, field="crm")]
    review = decide_review(CERTIFICATE, [PERIOD], rules, 0.99)
    assert review.required
    assert review.reasons == ("validation_failed:crm_format",)


def test_uncertain_classification_requires_review():
    review = decide_review(CERTIFICATE, [PERIOD], [], 0.7999)
    assert review.required
    assert review.reasons == ("uncertain_classification",)


def test_triggered_guardrail_requires_review():
    review = decide_review(CERTIFICATE, [PERIOD], [], 0.99, guardrail_triggered=True)
    assert review.required
    assert review.reasons == ("guardrail_triggered",)


def test_marginal_document_quality_requires_review():
    review = decide_review(CERTIFICATE, [PERIOD], [], 0.99, marginal_quality=True)
    assert review.required
    assert review.reasons == ("marginal_quality",)


def test_valid_document_at_classification_threshold_needs_no_review():
    review = decide_review(CERTIFICATE, [PERIOD], [], 0.8)
    assert not review.required
    assert review.reasons == ()


def test_repeated_validation_failure_has_one_review_reason():
    rules = [Validation("crm_format", False, field="crm")] * 2
    review = decide_review(CERTIFICATE, [PERIOD], rules, 0.99)
    assert review.reasons == ("validation_failed:crm_format",)


def test_a_blocked_output_becomes_review_and_never_returns_the_content() -> None:
    """O sétimo gatilho, ligado ponta a ponta.

    Antes disto, `GuardrailTriggered` subia até o tratador genérico e virava `internal_error`: o
    motivo de revisão existia no contrato e era inalcançável pelo pipeline. Um motivo que ninguém
    consegue produzir é um motivo que ninguém revisou.
    """
    from dataclasses import replace as substituir

    from adapters.fakes.guardrail import GuardedLlm
    from entrypoints.bootstrap import build_analyzer, build_dependencies
    from usecases.ports import GuardrailTriggered

    class OpinativoLlm:
        """Um modelo que devolve opinião clínica onde deveria devolver um campo."""

        def __init__(self, inner):
            self._inner = inner

        def classify(self, pages):
            return self._inner.classify(pages)

        def extract(self, pages, document_type, prompt_version):
            extracao = self._inner.extract(pages, document_type, prompt_version)
            campos = list(extracao.fields)
            campos[0] = substituir(
                campos[0], value="O afastamento deveria ter recebido mais dias de repouso"
            )
            return substituir(extracao, fields=tuple(campos))

    dependencias = build_dependencies("fake")
    guardado = GuardedLlm(OpinativoLlm(dependencias.llm))
    caminho = Path(__file__).resolve().parents[2] / "samples/atestado_01_pdf_nativo.pdf"

    analise = build_analyzer(dependencies=substituir(dependencias, llm=guardado))(
        caminho.read_bytes()
    )

    assert analise.review.required
    assert analise.review.reasons == ("guardrail_triggered",)
    assert analise.fields == [], "saída bloqueada não produz campo"
    assert analise.capabilities["extraction"] == "unavailable"

    # O conteúdo bloqueado não aparece em lugar nenhum da resposta.
    serializada = repr(analise)
    assert "repouso" not in serializada
    assert GuardrailTriggered("x").topic == "x"
