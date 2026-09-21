from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime

from core.analysis import Classification, Extraction, KnowledgeReference
from core.document import DocumentType, Page, RecognisedPage


class OcrPort(ABC):
    @abstractmethod
    def read(self, page: Page) -> RecognisedPage: ...


class GuardrailTriggered(RuntimeError):
    def __init__(self, topic: str) -> None:
        super().__init__(f"a política do guardrail bloqueou a saída: {topic}")
        self.topic = topic


class LlmPort(ABC):
    @abstractmethod
    def classify(self, pages: Sequence[Page]) -> Classification: ...

    @abstractmethod
    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction: ...


class KnowledgeRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]: ...


class MetricsPort(ABC):
    @abstractmethod
    def increment(self, name: str, dimensions: Mapping[str, str]) -> None: ...

    @abstractmethod
    def observe(
        self, name: str, value: float, unit: str, dimensions: Mapping[str, str]
    ) -> None: ...


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...
