from collections.abc import Mapping, Sequence
from typing import Any

from adapters.aws.clients import build_client
from core.analysis import KnowledgeReference
from usecases.ports import KnowledgeRetriever

VERSION_ATTRIBUTE = "_version"
UNKNOWN_VERSION = "unknown"


def _attribute(item: Mapping[str, Any], key: str) -> str | None:
    for attribute in item.get("DocumentAttributes", []):
        if attribute.get("Key") == key:
            return attribute.get("Value", {}).get("StringValue")
    return None


class KendraRetriever(KnowledgeRetriever):
    def __init__(
        self,
        index_id: str,
        attribute_filter: Mapping[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self._index_id = index_id
        self._attribute_filter = attribute_filter
        self._client = client if client is not None else build_client("kendra")

    def retrieve(self, query: str, top: int = 3) -> Sequence[KnowledgeReference]:
        request: dict[str, Any] = {
            "IndexId": self._index_id,
            "QueryText": query,
            "PageSize": top,
        }
        if self._attribute_filter:
            request["AttributeFilter"] = dict(self._attribute_filter)
        response = self._client.retrieve(**request)
        return [
            KnowledgeReference(
                source=item.get("DocumentTitle") or item.get("DocumentId", ""),
                version=_attribute(item, VERSION_ATTRIBUTE) or UNKNOWN_VERSION,
                excerpt=item.get("Content", ""),
                uri=item.get("DocumentURI"),
            )
            for item in response.get("ResultItems", [])[:top]
        ]
