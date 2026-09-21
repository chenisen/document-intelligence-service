"""O conjunto de referência indexado, para os dublês responderem sem arquivo gravado.

Antes isto era um cassete: um JSON por página, gerado por um script, guardado em `tests/fixtures/` e
indexado pelo hash da imagem. Três problemas mataram esse desenho.

* **Não provava o que parecia provar.** O cassete guardava a forma do nosso `RecognisedPage`, não a
  do Textract. Quem prova que o adapter entende a resposta real da AWS são os testes com
  `botocore.Stubber`, que usam a forma real da API.
* **Duas fontes de verdade em trava.** O gabarito e os cassetes precisavam ser regerados juntos, e
  qualquer byte diferente num documento invalidava a chave em silêncio.
* **Lixo acumulado.** O gerador escrevia por chave e nunca apagava, então sobravam cassetes órfãos
  de documentos que não existiam mais.

Agora o índice é construído em memória a partir da única fonte que já existia, o
`samples/gabarito.json` mais os próprios documentos. Custa cerca de 0,3 s uma vez por processo e não
deixa artefato.

O que estes dublês **não** provam, e nunca provaram: qualidade de extração. Devolvem o gabarito,
então comparar a resposta com o gabarito compara o gabarito com ele mesmo. Qualidade só a
avaliação contra conta real mede, e o relatório diz isso de si mesmo.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from adapters.documents import detect_format, pages_of, read_pdf
from core.document import DocumentType, Page, SourceFormat

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
GABARITO = SAMPLES / "gabarito.json"

# Confiança de campo com evidência localizada, e de campo sem ela. Existem para exercitar o
# limiar, não para significar alguma coisa.
CONFIANTE = 0.96
INCERTO = 0.25
OCR_CONFIDENCE = 96.0

TIPOS: dict[str, str | None] = {
    "atestado_medico": "medical_certificate",
    "resultado_avaliacao_medica": "medical_assessment_result",
    "aso": None,
    "fora_do_escopo": None,
}

CAMPOS = {
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

ROTULOS = {
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

OUTCOMES = {"Deferido": "granted", "Indeferido": "denied"}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def contract_value(name: str, value: Any) -> Any:
    """O gabarito fala a língua do documento; o contrato tem vocabulário próprio."""
    if value is None:
        return None
    if name in {"issue_date", "assessment_date"}:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    if name == "outcome":
        return OUTCOMES[value]
    if name == "crm":
        return {"number": value["numero"], "state": value["uf"]}
    if name in {"leave_period", "granted_period"}:
        periodo = {
            "start": contract_value("issue_date", value["inicio"]),
            "end": contract_value("issue_date", value["fim"]),
        }
        if "dias" in value:
            periodo["days"] = value["dias"]
        return periodo
    return value


def procurado(value: Any) -> str | None:
    """O que uma pessoa procuraria na página para achar este campo."""
    if value is None:
        return None
    if isinstance(value, dict):
        for chave in ("inicio", "numero"):
            if chave in value:
                return str(value[chave])
        return None
    return str(value)


def pagina_sintetica(campos: dict[str, Any]) -> str:
    """Uma página plausível de texto reconhecido, montada a partir do gabarito.

    Só é usada para documentos que não têm camada de texto. Onde há texto real no PDF, é o texto
    real que responde.
    """
    linhas = []
    for portugues, valor in campos.items():
        nome = CAMPOS.get(portugues, portugues)
        agulha = procurado(valor)
        if agulha is None:
            continue
        if nome == "leave_period":
            linhas.append(
                f"Afastamento de {valor['inicio']} a {valor['fim']}, por {valor['dias']} dia(s)"
            )
        elif nome == "granted_period":
            linhas.append(f"Periodo concedido de {valor['inicio']} a {valor['fim']}")
        elif nome == "crm":
            linhas.append(f"CRM/{valor['uf']} {valor['numero']}")
        else:
            linhas.append(f"{ROTULOS.get(nome, nome)}: {agulha}")
    return "\n".join(linhas)


@dataclass(frozen=True)
class Caso:
    """Um documento do conjunto, com o que cada dublê precisa devolver."""

    document_type: DocumentType | None
    textos: tuple[str, ...]
    campos: dict[str, Any]


@lru_cache(maxsize=1)
def indice() -> tuple[dict[str, tuple[Caso, int]], dict[str, Caso]]:
    """Por página, para o OCR; por documento inteiro, para o modelo.

    Construído uma vez por processo. `lru_cache` é o cache: não há estado global mutável.
    """
    por_pagina: dict[str, tuple[Caso, int]] = {}
    por_documento: dict[str, Caso] = {}

    for bruto in json.loads(GABARITO.read_text(encoding="utf-8")):
        conteudo = (SAMPLES / bruto["arquivo"]).read_bytes()
        paginas = pages_of(conteudo)

        if detect_format(conteudo) is SourceFormat.PDF and any(read_pdf(conteudo)[0]):
            textos = tuple(read_pdf(conteudo)[1])
        else:
            textos = (pagina_sintetica(bruto["campos"]),)

        caso = Caso(
            document_type=(
                DocumentType(TIPOS[bruto["tipo_documento"]])
                if TIPOS[bruto["tipo_documento"]]
                else None
            ),
            textos=textos,
            campos={CAMPOS.get(nome, nome): valor for nome, valor in bruto["campos"].items()},
        )
        for pagina in paginas:
            por_pagina[digest(pagina.image)] = (caso, pagina.number)
        por_documento[digest(b"".join(p.image for p in paginas))] = caso

    return por_pagina, por_documento


class DocumentoDesconhecido(LookupError):
    """O documento não está no conjunto de referência.

    A mensagem diz o que fazer, porque a causa quase sempre é a mesma: os documentos foram regerados
    e o índice ainda não viu este.
    """


def caso_da_pagina(page: Page) -> tuple[Caso, int]:
    por_pagina, _ = indice()
    chave = digest(page.image)
    if chave not in por_pagina:
        raise DocumentoDesconhecido(
            f"página {chave!r} não está no conjunto de referência. "
            f"O perfil `fake` só responde pelos documentos de `samples/`; rode `make fixtures`."
        )
    return por_pagina[chave]


def caso_do_documento(pages: Sequence[Page]) -> Caso:
    _, por_documento = indice()
    chave = digest(b"".join(p.image for p in pages))
    if chave not in por_documento:
        raise DocumentoDesconhecido(
            f"documento {chave!r} não está no conjunto de referência. "
            f"O perfil `fake` só responde pelos documentos de `samples/`; rode `make fixtures`."
        )
    return por_documento[chave]
