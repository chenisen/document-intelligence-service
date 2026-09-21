"""Reading route selection. Pure function, no I/O, no adapter.

Spec 0001. The route comes from the signal found while normalising, never from the file extension:
the extension is not even a parameter here, so it cannot decide anything.
"""

from core.document import NormalizedDocument, ReadingRoute

# Measured on the golden set: native PDFs yield 361 to 1035 characters per page, the scanned one
# yields 0. Per page and not on average, because a two-page PDF whose second page is scanned would
# pass on the average and then fail on reading.
MIN_CHARS_PER_PAGE = 150

# Below this, text is too small to read reliably. Above the side limit, the file is a scan artefact.
MIN_TEXT_HEIGHT_PX = 15
MAX_SIDE_PX = 10_000

# Textract returns confidence from 0 to 100. Below this the page is read again, multimodally.
MIN_OCR_CONFIDENCE = 80.0


def choose_route(document: NormalizedDocument) -> ReadingRoute:
    """First stage: decide before paying for any reading."""
    if document.smallest_text_height_px < MIN_TEXT_HEIGHT_PX:
        return ReadingRoute.REJECT
    if document.longest_side_px > MAX_SIDE_PX:
        return ReadingRoute.REJECT
    # Handwriting goes straight to the multimodal route:
    # OCR on handwriting costs without delivering.
    if document.has_handwriting_signal:
        return ReadingRoute.MULTIMODAL
    if document.has_reliable_text_layer:
        return ReadingRoute.DIRECT_TEXT
    return ReadingRoute.OCR


def reroute_after_ocr(route: ReadingRoute, ocr_confidence: float) -> ReadingRoute:
    """Second stage, and it costs money: a page rerouted here was read twice.

    One attempt only. There is no third reading.
    """
    if route is ReadingRoute.OCR and ocr_confidence < MIN_OCR_CONFIDENCE:
        return ReadingRoute.MULTIMODAL
    return route


def has_reliable_text_layer(chars_per_page: list[int]) -> bool:
    return bool(chars_per_page) and all(count >= MIN_CHARS_PER_PAGE for count in chars_per_page)
