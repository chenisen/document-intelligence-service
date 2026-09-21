import io
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw

from adapters import documents
from adapters.fakes.llm import StubLlm
from adapters.fakes.ocr import StubOcr
from core.document import DocumentType, ReadingRoute

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def image_bytes(size: tuple[int, int], foreground: int | None = None) -> bytes:
    with Image.new("L", size, color=255) as image:
        if foreground is not None:
            ImageDraw.Draw(image).rectangle((10, 10, size[0] - 10, 100), fill=foreground)
        with io.BytesIO() as output:
            image.save(output, format="PNG")
            return output.getvalue()


@pytest.mark.parametrize("foreground", [None, 248], ids=["blank", "low-contrast"])
def test_rejects_unreadable_pixels_at_normal_document_dimensions(
    foreground: int | None,
) -> None:
    result = documents.normalize(image_bytes((1200, 1800), foreground))

    assert result.route is ReadingRoute.REJECT


def two_page_pdf(second_size: tuple[int, int]) -> bytes:
    with (
        pdfium.PdfDocument((SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()) as pdf,
        closing(pdf.new_page(*second_size)),
        io.BytesIO() as output,
    ):
        pdf.save(output)
        return output.getvalue()


@pytest.mark.parametrize("second_size", [(595, 842), (100, 100)], ids=["blank", "tiny"])
def test_checks_quality_on_the_second_pdf_page(second_size: tuple[int, int]) -> None:
    assert documents.normalize(two_page_pdf(second_size)).route is ReadingRoute.REJECT


def test_checks_all_pdf_dimensions_before_any_rasterization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = two_page_pdf((6000, 6000))

    def forbidden_render(*args: object, **kwargs: object) -> None:
        pytest.fail("oversized PDF must be refused before allocating a page bitmap")

    monkeypatch.setattr(pdfium.PdfPage, "render", forbidden_render)

    assert documents.normalize(content).route is ReadingRoute.REJECT


@pytest.mark.parametrize("operation", [documents.read_pdf_text, documents.render_pdf_page])
def test_releases_pdf_resources_after_reading(operation, monkeypatch: pytest.MonkeyPatch) -> None:
    opened = []
    create = pdfium.PdfDocument
    render = pdfium.PdfPage.render

    def tracked_document(*args, **kwargs):
        document = create(*args, **kwargs)
        opened.append(document)
        return document

    def tracked_render(*args, **kwargs):
        bitmap = render(*args, **kwargs)
        opened.append(bitmap)
        return bitmap

    monkeypatch.setattr(pdfium, "PdfDocument", tracked_document)
    monkeypatch.setattr(pdfium.PdfPage, "render", tracked_render)
    content = (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()
    args = (content, 1) if operation is documents.render_pdf_page else (content,)

    operation(*args)

    assert opened
    assert all(resource.raw is None for resource in opened)


def test_releases_image_pixels_after_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = []
    create = Image.open

    def tracked_open(*args, **kwargs):
        image = create(*args, **kwargs)
        opened.append(image)
        return image

    monkeypatch.setattr(Image, "open", tracked_open)

    documents.normalize_image(image_bytes((1200, 1800), 0))

    with pytest.raises(ValueError, match="closed image"):
        opened[0].getpixel((0, 0))


def test_the_reference_index_keeps_each_page_text_separate() -> None:
    conteudo = (SAMPLES / "atestado_08_duas_paginas.pdf").read_bytes()
    paginas = documents.render_document_pages(conteudo)

    textos = [StubOcr().read(pagina).text for pagina in paginas]

    assert len(textos) == 2
    assert "ANEXO AO ATESTADO" not in textos[0]
    assert "ANEXO AO ATESTADO" in textos[1]
    assert "Carlos Eduardo Ferraz Lopes" in textos[0]


def test_evidence_names_the_page_where_the_text_was_found() -> None:
    conteudo = (SAMPLES / "atestado_08_duas_paginas.pdf").read_bytes()
    paginas = documents.render_document_pages(conteudo)

    extracao = StubLlm().extract(paginas, DocumentType.MEDICAL_CERTIFICATE, "v1")

    paciente = next(campo for campo in extracao.fields if campo.name == "patient_name")
    assert paciente.evidence is not None
    assert paciente.evidence.page == 1
    assert "Carlos Eduardo Ferraz Lopes" in paciente.evidence.text
