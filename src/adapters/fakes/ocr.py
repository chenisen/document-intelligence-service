from adapters.fakes.reference import OCR_CONFIDENCE, reference_case_for_page
from core.document import Page, RecognisedPage
from usecases.ports import OcrPort


class StubOcr(OcrPort):
    def read(self, page: Page) -> RecognisedPage:
        reference_case, page_number = reference_case_for_page(page)
        page_text = (
            reference_case.page_texts[page_number - 1]
            if page_number <= len(reference_case.page_texts)
            else reference_case.page_texts[0]
        )
        return RecognisedPage(number=page.number, text=page_text, confidence=OCR_CONFIDENCE)


class SpyOcr(OcrPort):
    def __init__(self, inner: OcrPort) -> None:
        self._inner = inner
        self.pages_read: list[int] = []

    def read(self, page: Page) -> RecognisedPage:
        self.pages_read.append(page.number)
        return self._inner.read(page)
