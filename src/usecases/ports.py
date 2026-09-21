"""The boundaries the domain knows about. Implementations live in adapters, never here.

Each port is an abstract base class rather than a Protocol on purpose: the adapter names the port it
implements, which is visible when reading the adapter, and a missing method fails at construction
instead of somewhere further down the call.

There is no storage port, and that absence is deliberate. The service keeps nothing: not the
document, not the result, not the review feedback. If a storage port feels missing, stop: either the
task is asking for something that belongs to the consumer, or it needs an ADR first.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime

from core.analysis import Classification, Extraction, KnowledgeReference
from core.document import DocumentType, Page, RecognisedPage


class OcrPort(ABC):
    """Optical character recognition, one page per call.

    One page per call is not a simplification: the synchronous operation reads a single page, which
    is why multipage PDFs are rasterised in-process and sent page by page.
    """

    @abstractmethod
    def read(self, page: Page) -> RecognisedPage: ...


class GuardrailTriggered(RuntimeError):
    """A política do guardrail bloqueou a saída do modelo.

    Faz parte do contrato do `LlmPort`: quem implementa pode levantá-la, e o caso de uso trata. Ela
    vive aqui, e não no adapter, porque o adapter real e o dublê precisam levantar o **mesmo**
    tipo — senão o pipeline trataria um e deixaria o outro virar erro genérico.

    A mensagem nomeia o tópico violado, nunca o texto bloqueado: devolver o conteúdo derrotaria o
    propósito de tê-lo bloqueado.
    """

    def __init__(self, topic: str) -> None:
        super().__init__(f"a política do guardrail bloqueou a saída: {topic}")
        self.topic = topic


class LlmPort(ABC):
    """The generative model. One port, two operations: it is the same model, the same guardrail and
    the same cassette, so splitting it into a classifier and an extractor would only duplicate the
    adapter."""

    @abstractmethod
    def classify(self, pages: Sequence[Page]) -> Classification: ...

    @abstractmethod
    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction: ...


class KnowledgeRetriever(ABC):
    """Retrieval of the applicable internal norm. Failure here degrades the analysis, it does not
    fail it: what was unavailable is reported in `capabilities`."""

    @abstractmethod
    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]: ...


class MetricsPort(ABC):
    """Emission of operational signal. Emission, not storage: nothing written here is readable back
    by the service, and that is what keeps the no-retention claim true."""

    @abstractmethod
    def increment(self, name: str, dimensions: Mapping[str, str]) -> None: ...

    @abstractmethod
    def observe(
        self, name: str, value: float, unit: str, dimensions: Mapping[str, str]
    ) -> None: ...


class Clock(ABC):
    """Time as a dependency, so provenance timestamps are assertable in tests."""

    @abstractmethod
    def now(self) -> datetime: ...
