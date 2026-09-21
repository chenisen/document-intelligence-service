"""Retrieval of the applicable internal norm, through Amazon Kendra `Retrieve`.

`Retrieve` rather than `Query` because what the answer needs is the passage itself, with where it
came from, and not a ranked list of documents to open.

The knowledge is the index, not this file: which norms exist, how they are written and how they are
ranked is ingestion, and a new norm never reaches a release of this service. Failure here degrades
the analysis instead of failing it, and what was unavailable is reported in `capabilities`.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from adapters.aws.clients import build_client
from core.analysis import KnowledgeReference
from usecases.ports import KnowledgeRetriever

# The attribute the ingestion writes the norm's version into. Without it the answer still carries
# the source, and the version is reported as unknown rather than guessed.
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
        # Comes from `config/kendra.json`. It is what keeps a revoked norm out of the answer in the
        # window between the revocation and the next data source sync, and it is the reason that
        # rule does not depend on ingestion having already run.
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
