"""Dublês de OCR: um responde pelo conjunto de referência, o outro só conta chamadas."""

from adapters.fakes.reference import OCR_CONFIDENCE, caso_da_pagina
from core.document import Page, RecognisedPage
from usecases.ports import OcrPort


class StubOcr(OcrPort):
    """Devolve o texto que aquela página tem, vindo do conjunto de referência.

    Não é um OCR: é a resposta que um OCR daria se acertasse tudo. Serve para o pipeline correr
    ponta a ponta sem conta e sem rede, e não prova nada sobre qualidade de leitura.
    """

    def read(self, page: Page) -> RecognisedPage:
        caso, numero = caso_da_pagina(page)
        texto = caso.textos[numero - 1] if numero <= len(caso.textos) else caso.textos[0]
        return RecognisedPage(number=page.number, text=texto, confidence=OCR_CONFIDENCE)


class SpyOcr(OcrPort):
    """Embrulha outro port e registra o que foi pedido.

    É assim que se prova que PDF com camada de texto **não** chega ao OCR, e que um PDF de duas
    páginas gera uma chamada por página. Sem contar, essas duas afirmações são só frases.
    """

    def __init__(self, inner: OcrPort) -> None:
        self._inner = inner
        self.pages_read: list[int] = []

    def read(self, page: Page) -> RecognisedPage:
        self.pages_read.append(page.number)
        return self._inner.read(page)
