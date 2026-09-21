"""Turning a received file into pages the rest of the pipeline can read.

Spec 0001. Everything here is local and free: no network, no credentials, no paid call. Refusing a
document happens before anything is paid for.
"""

import io
import math
from contextlib import closing
from dataclasses import replace
from typing import cast

import pillow_heif
import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image, ImageOps

from core.document import (
    NormalizedDocument,
    Page,
    ReadingRoute,
    SourceFormat,
)
from core.routing import MAX_SIDE_PX, MIN_TEXT_HEIGHT_PX, choose_route, has_reliable_text_layer

pillow_heif.register_heif_opener()

RASTER_SCALE = 2  # about 150 dpi from a 72 dpi page, enough for OCR without inflating the payload.

MAGIC = {
    b"%PDF": SourceFormat.PDF,
    b"\xff\xd8\xff": SourceFormat.JPEG,
    b"\x89PNG": SourceFormat.PNG,
}


def detect_format(content: bytes) -> SourceFormat:
    """The file extension never decides anything, so the bytes have to say what they are."""
    for magic, source_format in MAGIC.items():
        if content.startswith(magic):
            return source_format
    if content[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        return SourceFormat.HEIC
    raise ValueError("unsupported file format")


def _to_jpeg(image: Image.Image) -> bytes:
    with io.BytesIO() as buffer, closing(image.convert("RGB")) as rgb:
        rgb.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


def _text_height(image: Image.Image) -> int:
    # ponytail: global contrast catches blank/faded pages, not blur or dark noise; add those
    # metrics only against labelled quality cases.
    with closing(image.convert("L")) as grayscale:
        darkest, lightest = cast(tuple[int, int], grayscale.getextrema())
    if lightest - darkest < 20:
        return 0
    # ponytail: this estimates body text from page height, not individual glyphs; replace with
    # measured glyph heights if a labelled quality set shows this guard accepts unreadable text.
    return max(1, int(image.height * 0.015))


def normalize_image(content: bytes) -> tuple[Page, int]:
    """HEIC becomes JPEG and rotation is fixed before any quality measurement.

    Returns the page and an estimate of the smallest text height, used to refuse what is unreadable.
    """
    with closing(Image.open(io.BytesIO(content))) as image:
        ImageOps.exif_transpose(image, in_place=True)
        text_height = _text_height(image)
        page = Page(number=1, image=_to_jpeg(image), width=image.width, height=image.height)
        return page, text_height


def read_pdf(content: bytes) -> tuple[list[int], list[str]]:
    """Characters and text per page, without rasterising anything."""
    texts = []
    with pdfium.PdfDocument(content) as document:
        for i in range(len(document)):
            with closing(document[i]) as page, closing(page.get_textpage()) as textpage:
                texts.append((textpage.get_text_bounded() or "").strip())
    return [len(text) for text in texts], texts


def rasterize(content: bytes, page_number: int) -> Page:
    """One page at a time, because the synchronous OCR operation reads one page per call."""
    with (
        pdfium.PdfDocument(content) as document,
        closing(document[page_number - 1]) as page,
        closing(page.render(scale=RASTER_SCALE)) as bitmap,
        closing(bitmap.to_pil()) as image,
    ):
        return Page(
            number=page_number, image=_to_jpeg(image), width=image.width, height=image.height
        )


def normalize(content: bytes, has_handwriting_signal: bool = False) -> NormalizedDocument:
    source_format = detect_format(content)

    if source_format is SourceFormat.PDF:
        chars_per_page, _ = read_pdf(content)
        sizes = []
        with pdfium.PdfDocument(content) as pdf:
            for i in range(len(pdf)):
                with closing(pdf[i]) as page:
                    sizes.append(tuple(math.ceil(side * RASTER_SCALE) for side in page.get_size()))
        longest_side = max((max(size) for size in sizes), default=0)
        text_height = min((int(height * 0.015) for _, height in sizes), default=0)
        # Check every page's dimensions before allocating even the first bitmap.
        if longest_side <= MAX_SIDE_PX and text_height >= MIN_TEXT_HEIGHT_PX:
            for number in range(1, len(sizes) + 1):
                rendered = rasterize(content, number)
                with closing(Image.open(io.BytesIO(rendered.image))) as image:
                    text_height = min(text_height, _text_height(image))
        document = NormalizedDocument(
            source_format=source_format,
            page_count=len(chars_per_page),
            has_reliable_text_layer=has_reliable_text_layer(chars_per_page),
            has_handwriting_signal=has_handwriting_signal,
            smallest_text_height_px=text_height,
            longest_side_px=longest_side,
            route=ReadingRoute.OCR,
        )
    else:
        with closing(Image.open(io.BytesIO(content))) as image:
            longest_side = max(image.size)
            text_height = 0
            if longest_side <= MAX_SIDE_PX:
                ImageOps.exif_transpose(image, in_place=True)
                text_height = _text_height(image)
        document = NormalizedDocument(
            source_format=source_format,
            page_count=1,
            has_reliable_text_layer=False,
            has_handwriting_signal=has_handwriting_signal,
            smallest_text_height_px=text_height,
            longest_side_px=longest_side,
            route=ReadingRoute.OCR,
        )

    return replace(document, route=choose_route(document))


def pages_of(content: bytes) -> list[Page]:
    if detect_format(content) is SourceFormat.PDF:
        chars_per_page, _ = read_pdf(content)
        return [rasterize(content, i + 1) for i in range(len(chars_per_page))]
    return [normalize_image(content)[0]]
