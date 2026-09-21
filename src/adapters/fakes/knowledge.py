import json
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from core.analysis import KnowledgeReference
from usecases.ports import KnowledgeRetriever

CORPUS = Path(__file__).resolve().parents[3] / "knowledge" / "normas.json"


def _normalize_search_text(text: str) -> str:
    decomposed_text = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed_text if not unicodedata.combining(char))


class FakeKnowledgeRetriever(KnowledgeRetriever):
    def __init__(self, corpus: Path = CORPUS) -> None:
        norms = json.loads(corpus.read_text(encoding="utf-8"))["normas"]
        self._norms = [norm for norm in norms if norm.get("status") != "revogada"]

    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]:
        query_terms = set(_normalize_search_text(query).split())
        scored_norms = [
            (len(query_terms & {_normalize_search_text(word) for word in norm["keywords"]}), norm)
            for norm in self._norms
        ]
        return [
            KnowledgeReference(
                source=norm["source"], version=norm["version"], excerpt=norm["excerpt"]
            )
            for score, norm in sorted(scored_norms, key=lambda pair: -pair[0])
            if score > 0
        ][:top]


class FailingKnowledgeRetriever(KnowledgeRetriever):
    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]:
        raise ConnectionError("knowledge index unavailable")
