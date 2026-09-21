from dataclasses import dataclass
from enum import Enum

MAX_FILE_BYTES = 4 * 1024 * 1024


class SourceFormat(Enum):
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    HEIC = "heic"


class DocumentType(Enum):
    MEDICAL_CERTIFICATE = "medical_certificate"
    MEDICAL_ASSESSMENT_RESULT = "medical_assessment_result"


class ReadingRoute(Enum):
    DIRECT_TEXT = "direct_text"
    OCR = "ocr"
    MULTIMODAL = "multimodal"
    REJECT = "reject"


@dataclass(frozen=True)
class Page:
    number: int
    image: bytes
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"page numbering starts at 1, got {self.number}")


@dataclass(frozen=True)
class NormalizedDocument:
    source_format: SourceFormat
    page_count: int
    has_reliable_text_layer: bool
    has_handwriting_signal: bool
    smallest_text_height_px: int
    longest_side_px: int
    route: ReadingRoute


@dataclass(frozen=True)
class RecognisedPage:
    number: int
    text: str
    confidence: float
