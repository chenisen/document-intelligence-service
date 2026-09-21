"""The document as the service sees it, before and after normalisation."""

from dataclasses import dataclass
from enum import Enum

# Practical ceiling for a synchronous invocation behind the HTTP entry point, once the binary
# body is encoded. It follows from the chosen runtime, and it is declared in the contract so the
# caller can shrink the file before calling instead of discovering the limit by failing.
MAX_FILE_BYTES = 4 * 1024 * 1024


class SourceFormat(Enum):
    """File formats accepted at the edge. Accepting all of them is a requirement; guaranteeing the
    same quality across all of them is not, and quality is measured per format."""

    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    HEIC = "heic"


class DocumentType(Enum):
    """Document types the registry supports. Anything else is refused rather than guessed at."""

    MEDICAL_CERTIFICATE = "medical_certificate"
    MEDICAL_ASSESSMENT_RESULT = "medical_assessment_result"


class ReadingRoute(Enum):
    """How the document will be read. Chosen from the signal found while normalising, never from the
    file extension."""

    DIRECT_TEXT = "direct_text"
    OCR = "ocr"
    MULTIMODAL = "multimodal"
    REJECT = "reject"


@dataclass(frozen=True)
class Page:
    """One page ready to be read: already converted, already de-rotated."""

    number: int
    image: bytes
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"page numbering starts at 1, got {self.number}")


@dataclass(frozen=True)
class NormalizedDocument:
    """What normalisation produces, and the only thing routing is allowed to look at."""

    source_format: SourceFormat
    page_count: int
    has_reliable_text_layer: bool
    has_handwriting_signal: bool
    smallest_text_height_px: int
    longest_side_px: int
    route: ReadingRoute


@dataclass(frozen=True)
class RecognisedPage:
    """What the OCR port returns for one page.

    No engine-specific structure crosses this boundary.
    """

    number: int
    text: str
    confidence: float
