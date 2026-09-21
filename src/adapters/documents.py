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

PDF_RENDER_SCALE = 2
MIN_IMAGE_CONTRAST = 20
ESTIMATED_TEXT_HEIGHT_RATIO = 0.015

FORMAT_SIGNATURES = {
    b"%PDF": SourceFormat.PDF,
    b"\xff\xd8\xff": SourceFormat.JPEG,
    b"\x89PNG": SourceFormat.PNG,
}


def detect_format(content: bytes) -> SourceFormat:
    for signature, source_format in FORMAT_SIGNATURES.items():
        if content.startswith(signature):
            return source_format
    if content[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        return SourceFormat.HEIC
    raise ValueError("unsupported file format")


def _encode_jpeg(image: Image.Image) -> bytes:
    with io.BytesIO() as buffer, closing(image.convert("RGB")) as rgb_image:
        rgb_image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


def _estimate_text_height(image: Image.Image) -> int:
    with closing(image.convert("L")) as grayscale:
        darkest, lightest = cast(tuple[int, int], grayscale.getextrema())
    if lightest - darkest < MIN_IMAGE_CONTRAST:
        return 0
    return max(1, int(image.height * ESTIMATED_TEXT_HEIGHT_RATIO))


def normalize_image(content: bytes) -> tuple[Page, int]:
    with closing(Image.open(io.BytesIO(content))) as image:
        ImageOps.exif_transpose(image, in_place=True)
        estimated_text_height = _estimate_text_height(image)
        page = Page(number=1, image=_encode_jpeg(image), width=image.width, height=image.height)
        return page, estimated_text_height


def read_pdf_text(content: bytes) -> tuple[list[int], list[str]]:
    texts = []
    with pdfium.PdfDocument(content) as document:
        for page_index in range(len(document)):
            with closing(document[page_index]) as page, closing(page.get_textpage()) as text_page:
                texts.append((text_page.get_text_bounded() or "").strip())
    return [len(text) for text in texts], texts


def render_pdf_page(content: bytes, page_number: int) -> Page:
    with (
        pdfium.PdfDocument(content) as document,
        closing(document[page_number - 1]) as page,
        closing(page.render(scale=PDF_RENDER_SCALE)) as bitmap,
        closing(bitmap.to_pil()) as image,
    ):
        return Page(
            number=page_number, image=_encode_jpeg(image), width=image.width, height=image.height
        )


def normalize(content: bytes, has_handwriting_signal: bool = False) -> NormalizedDocument:
    source_format = detect_format(content)

    if source_format is SourceFormat.PDF:
        chars_per_page, _ = read_pdf_text(content)
        page_sizes = []
        with pdfium.PdfDocument(content) as pdf:
            for page_index in range(len(pdf)):
                with closing(pdf[page_index]) as page:
                    page_sizes.append(
                        tuple(math.ceil(side * PDF_RENDER_SCALE) for side in page.get_size())
                    )
        longest_side = max((max(size) for size in page_sizes), default=0)
        estimated_text_height = min(
            (int(height * ESTIMATED_TEXT_HEIGHT_RATIO) for _, height in page_sizes), default=0
        )
        if longest_side <= MAX_SIDE_PX and estimated_text_height >= MIN_TEXT_HEIGHT_PX:
            for number in range(1, len(page_sizes) + 1):
                rendered_page = render_pdf_page(content, number)
                with closing(Image.open(io.BytesIO(rendered_page.image))) as image:
                    estimated_text_height = min(estimated_text_height, _estimate_text_height(image))
        document = NormalizedDocument(
            source_format=source_format,
            page_count=len(chars_per_page),
            has_reliable_text_layer=has_reliable_text_layer(chars_per_page),
            has_handwriting_signal=has_handwriting_signal,
            smallest_text_height_px=estimated_text_height,
            longest_side_px=longest_side,
            route=ReadingRoute.OCR,
        )
    else:
        with closing(Image.open(io.BytesIO(content))) as image:
            longest_side = max(image.size)
            estimated_text_height = 0
            if longest_side <= MAX_SIDE_PX:
                ImageOps.exif_transpose(image, in_place=True)
                estimated_text_height = _estimate_text_height(image)
        document = NormalizedDocument(
            source_format=source_format,
            page_count=1,
            has_reliable_text_layer=False,
            has_handwriting_signal=has_handwriting_signal,
            smallest_text_height_px=estimated_text_height,
            longest_side_px=longest_side,
            route=ReadingRoute.OCR,
        )

    return replace(document, route=choose_route(document))


def render_document_pages(content: bytes) -> list[Page]:
    if detect_format(content) is SourceFormat.PDF:
        chars_per_page, _ = read_pdf_text(content)
        return [
            render_pdf_page(content, page_index + 1) for page_index in range(len(chars_per_page))
        ]
    return [normalize_image(content)[0]]
