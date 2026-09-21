from __future__ import annotations

import json
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pillow_heif
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

pillow_heif.register_heif_opener()

rl_config.invariant = 1

random.seed(20260918)
np.random.seed(20260918)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
WATERMARK = "DOCUMENTO SINTETICO GERADO PARA TESTE AUTOMATIZADO - SEM VALIDADE LEGAL"
PDF_FIXED_METADATA = {"creationDate": "D:20260918000000Z", "modDate": "D:20260918000000Z"}
VALIDATION_NOTICE = "VALIDAR EM: exemplo.invalido/validacao"

CANDIDATE_FONT_PATHS = (
    "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    "/Library/Fonts/Arial Italic.ttf",
)


def available_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in CANDIDATE_FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


@dataclass
class Doctor:
    name: str
    crm: str
    state: str
    site: str
    cnes: str
    address: str
    neighborhood: str
    city: str
    phone: str


@dataclass
class Certificate:
    patient: str
    document: str
    days: int
    start: str
    end: str
    cid: str | None
    notes: str
    issue_date: str
    doctor: Doctor


@dataclass
class Assessment:
    protocol: str
    applicant: str
    document: str
    assessment_type: str
    assessment_date: str
    outcome: str
    period_start: str | None
    period_end: str | None
    rationale: str
    issue_date: str
    doctor: Doctor


DOCTORS = [
    Doctor("Helena Vasconcelos Prado", "999001", "SP", "Clinica Sinteticas Sao Paulo", "9999001",
           "Rua das Figueiras Falsas, 1200", "Vila Exemplo", "Sao Paulo", "(11) 5555-0101"),
    Doctor("Rogério Aparecido Tanaka", "999042", "SP", "Ambulatorio Modelo Zona Sul", "9999042",
           "Avenida dos Testes, 45", "Jardim Amostra", "Sao Paulo", "(11) 5555-0142"),
    Doctor("Luís Otávio Mendonça Sá", "999317", "MG", "Centro Medico Fictus", "9999317",
           "Rua Sem Numero, 87", "Bairro Simulado", "Belo Horizonte", "(31) 5555-0317"),
]

SPELLED_OUT_DAYS = {1: "um", 2: "dois", 3: "tres", 5: "cinco", 7: "sete", 10: "dez", 15: "quinze", 30: "trinta"}


def _wrap_text(c: canvas.Canvas, text: str, width: float, font="Helvetica", size=11) -> list[str]:
    c.setFont(font, size)
    lines, current = [], ""
    for word in text.split():
        attempt = f"{current} {word}".strip()
        if c.stringWidth(attempt, font, size) <= width:
            current = attempt
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _header(c: canvas.Canvas, title: str, version: str) -> float:
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(1.2)
    c.line(MARGIN, PAGE_HEIGHT - 15 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 15 * mm)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 28 * mm, title)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 33 * mm, version)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(0.6)
    c.line(MARGIN, PAGE_HEIGHT - 37 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 37 * mm)
    return PAGE_HEIGHT - 50 * mm


def _doctor_block(c: canvas.Canvas, doctor: Doctor, issue_date: str, y: float) -> float:
    c.setLineWidth(0.4)
    c.line(MARGIN, y + 6 * mm, PAGE_WIDTH - MARGIN, y + 6 * mm)
    lines = [
        f"NOME DO(A) MEDICO(A): {doctor.name}          CRM: {doctor.crm}     UF: {doctor.state}",
        f"LOCAL DE ATENDIMENTO: {doctor.site}          CNES: {doctor.cnes}",
        f"ENDERECO: {doctor.address}          BAIRRO: {doctor.neighborhood}",
        f"CIDADE: {doctor.city}     UF: {doctor.state}     TELEFONE: {doctor.phone}",
        f"DATA DE EMISSAO: {issue_date}",
    ]
    c.setFont("Helvetica", 9)
    for line in lines:
        c.drawString(MARGIN, y, line)
        y -= 5.5 * mm
    return y


def _signature(c: canvas.Canvas, y: float) -> None:
    c.setLineWidth(0.6)
    c.line(PAGE_WIDTH / 2 - 45 * mm, y, PAGE_WIDTH / 2 + 45 * mm, y)
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_WIDTH / 2, y - 5 * mm, "ASSINATURA MEDICO(A)")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(PAGE_WIDTH / 2, y - 13 * mm, "VIA DIGITAL")
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawCentredString(PAGE_WIDTH / 2, y - 18 * mm, VALIDATION_NOTICE)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(0.65, 0.1, 0.1)
    c.drawCentredString(PAGE_WIDTH / 2, 12 * mm, WATERMARK)
    c.setFillColorRGB(0, 0, 0)


def generate_certificate_pdf(certificate: Certificate, destination: Path, extra_pages: int = 0) -> None:
    c = canvas.Canvas(str(destination), pagesize=A4)
    y = _header(c, "ATESTADO MEDICO", "VERSAO 2.0 | ABRIL DE 2020")

    body = (
        f"Atesto que o(a) Sr.(a) {certificate.patient}, portador(a) do documento {certificate.document}, "
        f"necessita de afastamento de suas atividades laborais por {certificate.days} "
        f"({SPELLED_OUT_DAYS.get(certificate.days, certificate.days)}) dias, a partir de {certificate.start}, "
        f"encerrando-se em {certificate.end}."
    )
    for line in _wrap_text(c, body, PAGE_WIDTH - 2 * MARGIN, size=11):
        c.setFont("Helvetica", 11)
        c.drawString(MARGIN, y, line)
        y -= 6.5 * mm

    y -= 4 * mm
    if certificate.cid:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, f"CID: {certificate.cid}")
        y -= 8 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "OBSERVACOES:")
    y -= 6 * mm
    for line in _wrap_text(c, certificate.notes, PAGE_WIDTH - 2 * MARGIN, size=10):
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, line)
        y -= 5.5 * mm

    y = _doctor_block(c, certificate.doctor, certificate.issue_date, PAGE_HEIGHT - 150 * mm)
    _signature(c, y - 25 * mm)

    for i in range(extra_pages):
        c.showPage()
        y2 = _header(c, "ANEXO AO ATESTADO", f"PAGINA {i + 2}")
        c.setFont("Helvetica", 10)
        for line in _wrap_text(
            c,
            "Comprovante de comparecimento emitido pela unidade de atendimento, "
            "anexado ao atestado no mesmo arquivo. Este anexo existe para exercitar "
            "documento de mais de uma pagina no mesmo PDF.",
            PAGE_WIDTH - 2 * MARGIN,
            size=10,
        ):
            c.drawString(MARGIN, y2, line)
            y2 -= 5.5 * mm
        _signature(c, 80 * mm)
    c.save()


EXAM_TYPES = ["Admissional", "Periodico", "Retorno ao trabalho",
              "Mudanca de riscos ocupacionais", "Demissional"]


ASSESSMENT_TYPES = ["Avaliacao inicial", "Prorrogacao", "Recurso"]
OUTCOMES = ["Deferido", "Indeferido"]


def generate_assessment_pdf(assessment: Assessment, destination: Path) -> None:
    c = canvas.Canvas(str(destination), pagesize=A4)
    y = _header(c, "RESULTADO DE AVALIACAO MEDICA", "DOCUMENTO DE DECISAO | VERSAO 1.0")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "PROTOCOLO:")
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN + 27 * mm, y, assessment.protocol)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(PAGE_WIDTH - MARGIN - 70 * mm, y, "DATA DA AVALIACAO:")
    c.setFont("Helvetica", 10)
    c.drawString(PAGE_WIDTH - MARGIN - 26 * mm, y, assessment.assessment_date)
    y -= 9 * mm

    c.setLineWidth(0.4)
    c.line(MARGIN, y + 3 * mm, PAGE_WIDTH - MARGIN, y + 3 * mm)
    for label, value, width in [("REQUERENTE:", assessment.applicant, 26),
                                 ("DOCUMENTO:", assessment.document, 25)]:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, y, label)
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN + width * mm, y, value)
        y -= 6 * mm

    y -= 3 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, y, "TIPO DE AVALIACAO:")
    x = MARGIN + 36 * mm
    for option in ASSESSMENT_TYPES:
        c.rect(x, y - 0.8 * mm, 3 * mm, 3 * mm, stroke=1, fill=0)
        if option == assessment.assessment_type:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 0.55 * mm, y - 0.1 * mm, "X")
        c.setFont("Helvetica", 8)
        c.drawString(x + 4.5 * mm, y, option)
        x += (len(option) * 1.5 + 12) * mm
    y -= 12 * mm

    c.setLineWidth(1.0)
    c.rect(MARGIN, y - 6 * mm, PAGE_WIDTH - 2 * MARGIN, 14 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGIN + 5 * mm, y, f"DESFECHO: {assessment.outcome.upper()}")
    y -= 18 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "PERIODO CONCEDIDO:")
    c.setFont("Helvetica", 10)
    if assessment.period_start and assessment.period_end:
        c.drawString(MARGIN + 42 * mm, y, f"de {assessment.period_start} a {assessment.period_end}")
    else:
        c.drawString(MARGIN + 42 * mm, y, "nao se aplica")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "FUNDAMENTACAO:")
    y -= 6 * mm
    for line in _wrap_text(c, assessment.rationale, PAGE_WIDTH - 2 * MARGIN, size=10):
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, line)
        y -= 5.5 * mm

    y = _doctor_block(c, assessment.doctor, assessment.issue_date, PAGE_HEIGHT - 185 * mm)
    _signature(c, y - 20 * mm)
    c.save()


def rasterize(pdf: Path, dpi: int = 150, page: int = 0) -> Image.Image:
    doc = pdfium.PdfDocument(str(pdf))
    img = doc[page].render(scale=dpi / 72).to_pil().convert("RGB")
    doc.close()
    return img


def scanner_noise(image: Image.Image, intensity: float = 9.0) -> Image.Image:
    arr = np.asarray(image).astype(np.float32)
    arr += np.random.normal(0, intensity, arr.shape)
    arr = np.clip(arr, 0, 255)
    out = Image.fromarray(arr.astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(0.4))


def tilt(image: Image.Image, degrees: float) -> Image.Image:
    return image.rotate(degrees, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))


def perspective(image: Image.Image, strength: float = 0.045) -> Image.Image:
    w, h = image.size
    d = strength * w
    source_points = [(0, 0), (w, 0), (w, h), (0, h)]
    dest_points = [
        (d * 0.9, d * 0.4), (w - d * 0.3, d * 1.3), (w - d * 1.1, h - d * 0.5), (d * 0.4, h - d * 1.2)
    ]
    rows = []
    for (xd, yd), (xo, yo) in zip(dest_points, source_points, strict=True):
        rows.append([xd, yd, 1, 0, 0, 0, -xo * xd, -xo * yd])
        rows.append([0, 0, 0, xd, yd, 1, -yo * xd, -yo * yd])
    coefficients = np.linalg.solve(
        np.array(rows, dtype=np.float64),
        np.array([c for point in source_points for c in point], dtype=np.float64),
    )
    return image.convert("RGB").transform(
        (w, h), Image.PERSPECTIVE, tuple(coefficients), Image.BICUBIC, fillcolor=(245, 245, 243)
    )


def shadow(image: Image.Image) -> Image.Image:
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    gx = np.linspace(0.62, 1.04, w)
    gy = np.linspace(1.02, 0.78, h)
    mask = np.outer(gy, gx)[:, :, None]
    return Image.fromarray(np.clip(arr * mask, 0, 255).astype(np.uint8))


def screenshot(image: Image.Image) -> Image.Image:
    crop = image.crop((0, 0, image.size[0], int(image.size[1] * 0.58)))
    width = crop.size[0]
    bar_height = 44
    screen = Image.new("RGB", (width, crop.size[1] + bar_height), (238, 240, 243))
    draw = ImageDraw.Draw(screen)
    draw.rectangle([0, 0, width, bar_height], fill=(226, 229, 234))
    font = available_font(18)
    draw.text((16, bar_height // 2), "visualizador de anexos - atestado.pdf", font=font, fill=(70, 75, 85), anchor="lm")
    screen.paste(crop, (0, bar_height))
    return screen


@dataclass
class Case:
    arquivo: str
    tipo_documento: str
    formato: str
    dificuldade: str
    resultado_esperado: str
    campos: dict
    notas: list[str] = field(default_factory=list)


def certificate_answer(
    certificate: Certificate, filename: str, format_name: str, difficulty: str, notes=()
) -> Case:
    return Case(
        arquivo=filename,
        tipo_documento="atestado_medico",
        formato=format_name,
        dificuldade=difficulty,
        resultado_esperado="extracao_completa",
        campos={
            "paciente_nome": certificate.patient,
            "paciente_documento": certificate.document,
            "periodo_afastamento": {"inicio": certificate.start, "fim": certificate.end, "dias": certificate.days},
            "cid": certificate.cid,
            "medico_nome": certificate.doctor.name,
            "crm": {"numero": certificate.doctor.crm, "uf": certificate.doctor.state},
            "cnes": certificate.doctor.cnes,
            "data_emissao": certificate.issue_date,
        },
        notas=list(notes),
    )


PUBLISHED_FILENAMES = {
    "atestado_01_pdf_nativo.pdf",
    "atestado_02_pdf_digitalizado.pdf",
    "atestado_06_captura_tela.png",
    "atestado_07_foto.heic",
    "atestado_08_duas_paginas.pdf",
    "resultado_01_pdf_nativo.pdf",
    "resultado_02_indeferido_digitalizado.jpg",
}


def main(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[Case] = []

    certificate_1 = Certificate("Ana Beatriz Marques da Silva", "000.000.000-00", 3, "14/09/2026", "16/09/2026",
                                 "M54.5", "Repouso relativo e retorno a avaliacao se houver piora.",
                                 "14/09/2026", DOCTORS[0])
    certificate_2 = Certificate("Carlos Eduardo Ferraz Lopes", "000.000.000-00", 15, "01/09/2026", "15/09/2026",
                                 None, "Paciente orientado quanto ao retorno gradual as atividades.",
                                 "01/09/2026", DOCTORS[1])

    p = output_dir / "atestado_01_pdf_nativo.pdf"
    generate_certificate_pdf(certificate_1, p)
    cases.append(certificate_answer(certificate_1, p.name, "pdf_nativo", "facil",
                                     ["tem camada de texto: nao deve chamar OCR"]))

    img = scanner_noise(tilt(rasterize(p, 150), -1.4), 8)
    p2 = output_dir / "atestado_02_pdf_digitalizado.pdf"
    img.convert("RGB").save(p2, "PDF", resolution=150, **PDF_FIXED_METADATA)
    cases.append(certificate_answer(certificate_1, p2.name, "pdf_digitalizado", "media",
                                     ["sem camada de texto: exige OCR", "inclinacao de 1,4 grau"]))

    certificate_3 = Certificate("Thaís Nogueira Rebouças", "000.000.000-00", 5, "02/09/2026", "06/09/2026", "J11",
                                 "Retorno se houver febre persistente.", "02/09/2026", DOCTORS[1])
    tmp6 = output_dir / "_tmp_captura.pdf"
    generate_certificate_pdf(certificate_3, tmp6)
    p6 = output_dir / "atestado_06_captura_tela.png"
    screenshot(rasterize(tmp6, 150)).save(p6)
    tmp6.unlink()
    case_6 = certificate_answer(certificate_3, p6.name, "png_captura_tela", "media",
                                 ["imagem nitida, mas o documento esta cortado",
                                  "bloco do medico ausente: campos de CRM e CNES devem vir nulos"])
    case_6.resultado_esperado = "extracao_parcial"
    case_6.campos["medico_nome"] = None
    case_6.campos["crm"] = None
    case_6.campos["cnes"] = None
    case_6.campos["data_emissao"] = None
    cases.append(case_6)

    certificate_4 = Certificate("João Vítor Sampaio Rocha", "000.000.000-00", 2, "10/09/2026", "11/09/2026",
                                 "M54", "Afastamento por lombalgia aguda.", "10/09/2026", DOCTORS[2])
    tmp7 = output_dir / "_tmp_heic.pdf"
    generate_certificate_pdf(certificate_4, tmp7)
    p7 = output_dir / "atestado_07_foto.heic"
    shadow(perspective(scanner_noise(rasterize(tmp7, 180), 6))).convert("RGB").save(
        p7, format="HEIF", quality=70
    )
    tmp7.unlink()
    cases.append(certificate_answer(certificate_4, p7.name, "heic", "dificil",
                                     ["formato nao aceito pelo Textract: exige conversao no processo"]))

    p8 = output_dir / "atestado_08_duas_paginas.pdf"
    generate_certificate_pdf(certificate_2, p8, extra_pages=1)
    cases.append(certificate_answer(certificate_2, p8.name, "pdf_nativo_multipagina", "media",
                                     ["duas paginas: a operacao sincrona do Textract le apenas uma",
                                      "afastamento de 15 dias, limite do artigo 60 da Lei 8.213/91",
                                      "sem CID: o campo deve vir nulo, nao inferido"]))

    assessment_1 = Assessment(
        protocol="2026-AV-0000123", applicant="Cecília Andrade Peixoto", document="000.000.000-00",
        assessment_type="Avaliacao inicial", assessment_date="09/09/2026", outcome="Deferido",
        period_start="09/09/2026", period_end="08/10/2026",
        rationale=("Avaliacao presencial realizada na data indicada. Quadro compativel com a "
                   "documentacao apresentada, com limitacao funcional temporaria para as atividades "
                   "da funcao. Concedido o periodo acima, com reavaliacao ao termino."),
        issue_date="09/09/2026", doctor=DOCTORS[2],
    )
    assessment_2 = Assessment(
        protocol="2026-AV-0000417", applicant="Márcio Aurélio Bezerra", document="000.000.000-00",
        assessment_type="Prorrogacao", assessment_date="16/09/2026", outcome="Indeferido",
        period_start=None, period_end=None,
        rationale=("Nao foram identificados elementos que justifiquem a prorrogacao solicitada. "
                   "Documentacao apresentada nao demonstra agravamento em relacao a avaliacao anterior. "
                   "Requerente orientada quanto ao retorno as atividades."),
        issue_date="16/09/2026", doctor=DOCTORS[0],
    )

    def assessment_answer(
        assessment: Assessment, filename: str, format_name: str, difficulty: str, notes=()
    ) -> Case:
        period = None
        if assessment.period_start and assessment.period_end:
            period = {"inicio": assessment.period_start, "fim": assessment.period_end}
        return Case(
            arquivo=filename, tipo_documento="resultado_avaliacao_medica", formato=format_name,
            dificuldade=difficulty, resultado_esperado="extracao_completa",
            campos={
                "protocolo": assessment.protocol,
                "requerente_nome": assessment.applicant,
                "requerente_documento": assessment.document,
                "tipo_avaliacao": assessment.assessment_type,
                "data_avaliacao": assessment.assessment_date,
                "desfecho": assessment.outcome,
                "periodo_concedido": period,
                "medico_nome": assessment.doctor.name,
                "crm": {"numero": assessment.doctor.crm, "uf": assessment.doctor.state},
                "data_emissao": assessment.issue_date,
                "cid": None,
            },
            notas=list(notes),
        )

    p_res1 = output_dir / "resultado_01_pdf_nativo.pdf"
    generate_assessment_pdf(assessment_1, p_res1)
    cases.append(assessment_answer(assessment_1, p_res1.name, "pdf_nativo", "facil",
                                    ["desfecho vem de campo categorico em caixa destacada",
                                     "tipo de avaliacao vem de caixa marcada",
                                     "nao tem CID: o campo deve vir nulo"]))

    p_res2 = output_dir / "resultado_02_indeferido_digitalizado.jpg"
    tmp3 = output_dir / "_tmp_res2.pdf"
    generate_assessment_pdf(assessment_2, tmp3)
    scanner_noise(tilt(rasterize(tmp3, 150), -1.7), 9).convert("RGB").save(p_res2, "JPEG", quality=82)
    tmp3.unlink()
    cases.append(assessment_answer(assessment_2, p_res2.name, "jpeg_digitalizado", "dificil",
                                    ["desfecho indeferido: extrair errado inverte a decisao do fluxo",
                                     "periodo concedido nao se aplica e deve vir nulo, nunca inferido",
                                     "a fundamentacao e negativa, e e o texto que modelo tende a atropelar"]))

    discarded = [case for case in cases if case.arquivo not in PUBLISHED_FILENAMES]
    for case in discarded:
        (output_dir / case.arquivo).unlink(missing_ok=True)
    cases = [case for case in cases if case.arquivo in PUBLISHED_FILENAMES]
    assert len(cases) == len(PUBLISHED_FILENAMES), sorted(PUBLISHED_FILENAMES - {case.arquivo for case in cases})

    (output_dir / "answer_key.json").write_text(
        json.dumps([asdict(case) for case in cases], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for case in cases:
        print(f"{case.arquivo:42s} {case.tipo_documento:18s} {case.formato:24s} {case.dificuldade}")
    print(f"\n{len(cases)} casos publicados em {output_dir}, {len(discarded)} gerados e descartados")
    print("Os dublês montam o indice a partir destes arquivos e do gabarito, em memoria.")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
