"""OCR through Amazon Textract, one page per call.

One page per call is not a simplification: the synchronous `DetectDocumentText` operation reads a
single page, and the asynchronous one would require putting the document in a bucket, which this
service does not have. That is why multipage PDFs are rasterised in-process and sent page by page.

`DetectDocumentText` rather than `AnalyzeDocument` with `FORMS`: the pipeline only uses the lines,
which is what the evidence check searches, and `FORMS` costs about thirty times more per page for
key-value pairs nothing here reads.
"""

from typing import Any

from adapters.aws.clients import build_client
from core.document import Page, RecognisedPage
from usecases.ports import OcrPort

# A line is what a person reads, and it is what the evidence check looks for. Word blocks would
# fragment the excerpt the model has to quote.
LINE = "LINE"


class TextractOcr(OcrPort):
    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else build_client("textract")

    def read(self, page: Page) -> RecognisedPage:
        response = self._client.detect_document_text(Document={"Bytes": page.image})
        lines = [block for block in response.get("Blocks", []) if block["BlockType"] == LINE]
        text = "\n".join(line.get("Text", "") for line in lines)
        confidences = [line["Confidence"] for line in lines if "Confidence" in line]
        # The lowest confidence on the page, not the average: one illegible line is what sends the
        # page to the multimodal route, and an average would hide it behind the legible ones.
        return RecognisedPage(
            number=page.number, text=text, confidence=min(confidences, default=0.0)
        )
