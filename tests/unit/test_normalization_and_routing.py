"""Slice 1, spec 0001. Normalisation and reading route.

The whole table of the spec runs here, against the real files of the golden set. No network and no
credentials: every one of these is local and free, which is the point of refusing before paying.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from adapters.documents import detect_format, normalize, normalize_image, pages_of, read_pdf
from core.document import NormalizedDocument, ReadingRoute, SourceFormat
from core.routing import (
    MIN_OCR_CONFIDENCE,
    choose_route,
    has_reliable_text_layer,
    reroute_after_ocr,
)

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

# Spec 0001: every file of the reference set and the route its signal must choose. The point of the
# table is that the extension decides nothing — the two PDFs take different routes, and the three
# images take the same one their formats would not predict. A file above the size limit is absent on
# purpose: it is refused at the edge, before any NormalizedDocument exists.
ROUTES = [
    ("atestado_01_pdf_nativo.pdf", ReadingRoute.DIRECT_TEXT),
    ("atestado_02_pdf_digitalizado.pdf", ReadingRoute.OCR),
    ("atestado_06_captura_tela.png", ReadingRoute.OCR),
    ("atestado_07_foto.heic", ReadingRoute.OCR),
    ("atestado_08_duas_paginas.pdf", ReadingRoute.DIRECT_TEXT),
    ("resultado_01_pdf_nativo.pdf", ReadingRoute.DIRECT_TEXT),
    ("resultado_02_indeferido_digitalizado.jpg", ReadingRoute.OCR),
]


def signals(**overrides: object) -> NormalizedDocument:
    base = {
        "source_format": SourceFormat.PDF,
        "page_count": 1,
        "has_reliable_text_layer": False,
        "has_handwriting_signal": False,
        "smallest_text_height_px": 30,
        "longest_side_px": 2000,
        "route": ReadingRoute.OCR,
    }
    return NormalizedDocument(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(("filename", "expected"), ROUTES, ids=[name for name, _ in ROUTES])
def test_every_golden_set_file_lands_on_the_declared_route(
    filename: str, expected: ReadingRoute
) -> None:
    assert normalize((SAMPLES / filename).read_bytes()).route is expected


def test_converts_heic_to_jpeg() -> None:
    page, _ = normalize_image((SAMPLES / "atestado_07_foto.heic").read_bytes())

    assert page.image.startswith(b"\xff\xd8\xff")
    assert detect_format((SAMPLES / "atestado_07_foto.heic").read_bytes()) is SourceFormat.HEIC


def test_fixes_rotation_before_quality_assessment() -> None:
    """A page rotated by EXIF must come back upright, or every measurement after it is wrong."""
    with Image.new("RGB", (2000, 1000), "white") as image, io.BytesIO() as buffer:
        image.paste("black", (0, 0, 400, 1000))
        exif = Image.Exif()
        exif[274] = 6  # Display with a 90-degree clockwise rotation.
        image.save(buffer, format="JPEG", exif=exif)
        photo = buffer.getvalue()

    upright, text_height = normalize_image(photo)

    assert (upright.width, upright.height) == (1000, 2000)
    assert text_height == 30
    with Image.open(io.BytesIO(upright.image)) as pixels:
        assert pixels.size == (1000, 2000)
        assert pixels.getpixel((500, 200)) == (0, 0, 0)
        assert pixels.getpixel((500, 1800)) == (255, 255, 255)


def test_counts_pages_of_a_multipage_pdf() -> None:
    assert normalize((SAMPLES / "atestado_08_duas_paginas.pdf").read_bytes()).page_count == 2


def test_pdf_with_text_layer_chooses_direct_text() -> None:
    chars, texts = read_pdf((SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes())

    assert has_reliable_text_layer(chars)
    assert "afastamento" in texts[0].lower()


def test_scanned_pdf_chooses_ocr() -> None:
    chars, _ = read_pdf((SAMPLES / "atestado_02_pdf_digitalizado.pdf").read_bytes())

    assert chars == [0]
    assert not has_reliable_text_layer(chars)


def test_a_single_scanned_page_invalidates_the_whole_text_layer() -> None:
    """On the average this would pass, and then fail on reading. The rule is per page."""
    assert not has_reliable_text_layer([900, 0])
    assert has_reliable_text_layer([900, 361])


def test_handwriting_signal_chooses_multimodal() -> None:
    """OCR on handwriting costs without delivering, so it is skipped entirely."""
    assert choose_route(signals(has_handwriting_signal=True)) is ReadingRoute.MULTIMODAL


def test_low_ocr_confidence_reroutes_to_multimodal_once() -> None:
    once = reroute_after_ocr(ReadingRoute.OCR, MIN_OCR_CONFIDENCE - 1)
    assert once is ReadingRoute.MULTIMODAL
    # No third reading: what is already multimodal stays put.
    assert reroute_after_ocr(once, 0.0) is ReadingRoute.MULTIMODAL
    assert reroute_after_ocr(ReadingRoute.DIRECT_TEXT, 0.0) is ReadingRoute.DIRECT_TEXT


def test_file_extension_alone_does_not_decide_the_route() -> None:
    """The same bytes under a lying name route the same way: the extension is not a parameter."""
    lying = (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()

    assert normalize(lying).route is ReadingRoute.DIRECT_TEXT
    assert detect_format(lying) is SourceFormat.PDF


def test_rejects_below_the_minimum_text_height() -> None:
    assert choose_route(signals(smallest_text_height_px=14)) is ReadingRoute.REJECT


def test_rejects_above_the_maximum_side_length() -> None:
    assert choose_route(signals(longest_side_px=10_001)) is ReadingRoute.REJECT


def test_rasterises_a_multipage_pdf_page_by_page() -> None:
    pages = pages_of((SAMPLES / "atestado_08_duas_paginas.pdf").read_bytes())

    assert [page.number for page in pages] == [1, 2]
    assert all(page.image.startswith(b"\xff\xd8\xff") for page in pages)
