from core.document import NormalizedDocument, ReadingRoute

MIN_CHARS_PER_PAGE = 150

MIN_TEXT_HEIGHT_PX = 15
MAX_SIDE_PX = 10_000

MIN_OCR_CONFIDENCE = 80.0


def choose_route(document: NormalizedDocument) -> ReadingRoute:
    if document.smallest_text_height_px < MIN_TEXT_HEIGHT_PX:
        return ReadingRoute.REJECT
    if document.longest_side_px > MAX_SIDE_PX:
        return ReadingRoute.REJECT
    if document.has_handwriting_signal:
        return ReadingRoute.MULTIMODAL
    if document.has_reliable_text_layer:
        return ReadingRoute.DIRECT_TEXT
    return ReadingRoute.OCR


def reroute_after_ocr(route: ReadingRoute, ocr_confidence: float) -> ReadingRoute:
    if route is ReadingRoute.OCR and ocr_confidence < MIN_OCR_CONFIDENCE:
        return ReadingRoute.MULTIMODAL
    return route


def has_reliable_text_layer(chars_per_page: list[int]) -> bool:
    return bool(chars_per_page) and all(count >= MIN_CHARS_PER_PAGE for count in chars_per_page)
