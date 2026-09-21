from typing import Any

from adapters.aws.clients import build_client
from core.document import Page, RecognisedPage
from usecases.ports import OcrPort

LINE = "LINE"


class TextractOcr(OcrPort):
    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else build_client("textract")

    def read(self, page: Page) -> RecognisedPage:
        response = self._client.detect_document_text(Document={"Bytes": page.image})
        lines = [block for block in response.get("Blocks", []) if block["BlockType"] == LINE]
        text = "\n".join(line.get("Text", "") for line in lines)
        confidences = [line["Confidence"] for line in lines if "Confidence" in line]
        return RecognisedPage(
            number=page.number, text=text, confidence=min(confidences, default=0.0)
        )
