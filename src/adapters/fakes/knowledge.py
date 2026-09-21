"""Knowledge double, over the synthetic corpus of internal norms in `knowledge/`.

Word overlap, no ranking worth the name. It proves that the pipeline asks, receives, and reports
source and version. What it does **not** prove is retrieval quality, and only a real index does.

It does reproduce one rule of the index that is not about ranking: a revoked norm is never cited.
In a real deployment that happens at ingestion, because the document leaves the index; here it is a
filter, so the rule stays provable without an index.
"""

import json
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from core.analysis import KnowledgeReference
from usecases.ports import KnowledgeRetriever

CORPUS = Path(__file__).resolve().parents[3] / "knowledge" / "normas.json"


def fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in stripped if not unicodedata.combining(char))


class FakeKnowledgeRetriever(KnowledgeRetriever):
    def __init__(self, corpus: Path = CORPUS) -> None:
        norms = json.loads(corpus.read_text(encoding="utf-8"))["normas"]
        self._norms = [norm for norm in norms if norm.get("status") != "revogada"]

    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]:
        terms = set(fold(query).split())
        scored = [
            (len(terms & {fold(word) for word in norm["keywords"]}), norm) for norm in self._norms
        ]
        return [
            KnowledgeReference(
                source=norm["source"], version=norm["version"], excerpt=norm["excerpt"]
            )
            for score, norm in sorted(scored, key=lambda pair: -pair[0])
            if score > 0
        ][:top]


class FailingKnowledgeRetriever(KnowledgeRetriever):
    """Proves RF-16: enrichment failing degrades the answer, it does not fail it."""

    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]:
        raise ConnectionError("knowledge index unavailable")
