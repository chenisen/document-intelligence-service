import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from core.analysis import Classification, Extraction
from core.document import DocumentType, Page
from usecases.ports import GuardrailTriggered, LlmPort

GUARDRAIL_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "guardrails.json"
MIN_MATCHING_TOPIC_TERMS = 2


def _normalize_policy_text(text: str) -> str:
    decomposed_text = unicodedata.normalize("NFKD", text.lower())
    return "".join(
        character for character in decomposed_text if not unicodedata.combining(character)
    )


def denied_topic_terms(policy: dict) -> dict[str, tuple[str, ...]]:
    terms_by_topic: dict[str, tuple[str, ...]] = {}
    for topic in policy.get("topicsConfig", []):
        if topic.get("type") != "DENY":
            continue
        keywords: set[str] = set()
        for example in topic.get("examples", []):
            keywords.update(
                word for word in re.findall(r"[a-zá-úâ-ûã-õç]{5,}", _normalize_policy_text(example))
            )
        terms_by_topic[topic["name"]] = tuple(sorted(keywords))
    return terms_by_topic


class GuardedLlm(LlmPort):
    def __init__(self, inner: LlmPort, policy_path: Path = GUARDRAIL_POLICY_PATH) -> None:
        self._inner = inner
        self._denied_terms_by_topic = denied_topic_terms(
            json.loads(policy_path.read_text(encoding="utf-8"))
        )

    def _raise_if_topic_blocked(self, text: str) -> None:
        normalized_text = _normalize_policy_text(text)
        for topic, terms in self._denied_terms_by_topic.items():
            matching_term_count = sum(1 for term in terms if term in normalized_text)
            if matching_term_count >= MIN_MATCHING_TOPIC_TERMS:
                raise GuardrailTriggered(topic)

    def classify(self, pages: Sequence[Page]) -> Classification:
        return self._inner.classify(pages)

    def extract(
        self, pages: Sequence[Page], document_type: DocumentType, prompt_version: str
    ) -> Extraction:
        extraction = self._inner.extract(pages, document_type, prompt_version)
        for field in extraction.fields:
            if isinstance(field.value, str):
                self._raise_if_topic_blocked(field.value)
        return extraction
