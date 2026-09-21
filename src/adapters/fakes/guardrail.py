"""Guardrail simulado: aplica localmente a política declarada em `config/guardrails.json`.

Existe porque `guardrail_triggered` é um dos sete motivos de revisão do contrato, e sem isto ele é
**inalcançável fora de teste unitário**: o guardrail de verdade só intervém no Bedrock, e o perfil
`fake` não chama o Bedrock. Um motivo de revisão que ninguém consegue demonstrar é um motivo que
ninguém revisou.

O que este dublê **não** é: um guardrail. Ele casa termo, não entende texto. O guardrail de verdade
classifica intenção e é provisionado no Bedrock, fora deste repositório. O que se prova aqui é a
**ligação**: que uma saída bloqueada vira revisão com motivo estável em vez de erro genérico, e
que o conteúdo bloqueado não volta para o consumidor.
"""

import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from core.analysis import Classification, Extraction
from core.document import DocumentType, Page
from usecases.ports import GuardrailTriggered, LlmPort

POLITICA = Path(__file__).resolve().parents[3] / "config" / "guardrails.json"


def dobrar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def termos_negados(politica: dict) -> dict[str, tuple[str, ...]]:
    """Os termos de cada tópico negado, tirados dos próprios exemplos da política.

    Usar os exemplos como fonte é deliberado: eles já existem para o provisionamento, e assim a
    simulação não inventa um segundo vocabulário que poderia divergir do que será configurado.
    """
    negados: dict[str, tuple[str, ...]] = {}
    for topico in politica.get("topicsConfig", []):
        if topico.get("type") != "DENY":
            continue
        palavras: set[str] = set()
        for exemplo in topico.get("examples", []):
            palavras.update(p for p in re.findall(r"[a-zá-úâ-ûã-õç]{5,}", dobrar(exemplo)))
        negados[topico["name"]] = tuple(sorted(palavras))
    return negados


class GuardedLlm(LlmPort):
    """Embrulha outro `LlmPort` e aplica a política declarada sobre o que ele devolveu."""

    def __init__(self, inner: LlmPort, politica: Path = POLITICA) -> None:
        self._inner = inner
        self._negados = termos_negados(json.loads(politica.read_text(encoding="utf-8")))

    def _verificar(self, texto: str) -> None:
        dobrado = dobrar(texto)
        for topico, termos in self._negados.items():
            atingidos = sum(1 for termo in termos if termo in dobrado)
            # Dois termos, e não um: o guardrail de verdade classifica intenção, e uma palavra
            # isolada como "afastamento" aparece em documento legítimo o tempo todo.
            if atingidos >= 2:
                raise GuardrailTriggered(topico)

    def classify(self, pages: Sequence[Page]) -> Classification:
        return self._inner.classify(pages)

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        extracao = self._inner.extract(pages, document_type, prompt_version)
        for campo in extracao.fields:
            if isinstance(campo.value, str):
                self._verificar(campo.value)
        return extracao
