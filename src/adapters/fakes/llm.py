"""Dublê do modelo. Responde pelo conjunto de referência, sem chamar nada.

O modelo generativo não entra em teste unitário: ele não é determinístico nem a temperatura zero.
O que se afirma aqui é a ligação e a forma da resposta, nunca a qualidade dela.
"""

from collections.abc import Sequence

from adapters.fakes.reference import (
    CONFIANTE,
    INCERTO,
    caso_do_documento,
    contract_value,
    procurado,
)
from core.analysis import Classification, ExtractedField, Extraction
from core.document import DocumentType, Page
from core.values import Confidence, Evidence
from usecases.ports import LlmPort


def _evidencia(textos: Sequence[str], agulha: str | None) -> Evidence | None:
    """A linha onde o valor aparece, e a página dela.

    Localizar de verdade importa: é isto que faz a verificação de evidência do domínio ter o que
    verificar. Campo cujo valor não aparece em página nenhuma volta sem evidência e cai lá na
    frente, que é exatamente o comportamento a ser exercitado.
    """
    if not agulha:
        return None
    for numero, texto in enumerate(textos, 1):
        for linha in texto.splitlines():
            if agulha in linha:
                return Evidence(text=linha.strip(), page=numero)
    return None


class StubLlm(LlmPort):
    def classify(self, pages: Sequence[Page]) -> Classification:
        caso = caso_do_documento(pages)
        return Classification(
            document_type=caso.document_type,
            confidence=Confidence(0.97 if caso.document_type else 0.93),
        )

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        caso = caso_do_documento(pages)
        campos = []
        for nome, valor in caso.campos.items():
            evidencia = _evidencia(caso.textos, procurado(valor))
            campos.append(
                ExtractedField(
                    name=nome,
                    value=contract_value(nome, valor),
                    confidence=Confidence(CONFIANTE if evidencia else INCERTO),
                    evidence=evidencia,
                )
            )
        return Extraction(document_type=document_type, fields=tuple(campos))
