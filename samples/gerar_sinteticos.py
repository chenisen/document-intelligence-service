"""
Gera o conjunto de referência com gabarito do Document Intelligence Service.

Todos os documentos são SINTÉTICOS: nome, CRM, CNES, CPF e endereço são inventados,
os números de CRM são inválidos de propósito e cada arquivo carrega uma marca de
documento de teste. O layout segue os modelos públicos do Conselho Federal de Medicina
usados na Prescrição Eletrônica, apenas como referência de estrutura de campos.

Uso: python gerar_sinteticos.py [diretorio_de_saida]
"""
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

# Saida determinstica: sem isso o reportlab carimba CreationDate e um ID de documento novos a cada
# execucao, os PDFs mudam de hash, as imagens rasterizadas deles mudam junto, e todo cassete --
# indexado pelo hash da pagina -- passa a errar. Como os documentos nao sao versionados, regerar
# precisa produzir exatamente os mesmos bytes.
rl_config.invariant = 1

random.seed(20260918)
np.random.seed(20260918)

LARG, ALT = A4
MARGEM = 20 * mm
MARCA = "DOCUMENTO SINTETICO GERADO PARA TESTE AUTOMATIZADO - SEM VALIDADE LEGAL"
# O escritor de PDF do Pillow carimba a hora atual, entao ela e fixada pelo mesmo motivo do
# rl_config.invariant acima: regerar precisa produzir os mesmos bytes.
PDF_INVARIANTE = {"creationDate": "D:20260918000000Z", "modDate": "D:20260918000000Z"}
VALIDACAO = "VALIDAR EM: exemplo.invalido/validacao"

# Primeira fonte que existir na maquina. O ultimo recurso e a embutida do Pillow, que nao e bonita
# mas mantem `make samples` rodando em qualquer lugar: caminho fixo de fonte nao e portavel.
FONTES_POSSIVEIS = (
    "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    "/Library/Fonts/Arial Italic.ttf",
)


def fonte_disponivel(tamanho: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for caminho in FONTES_POSSIVEIS:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, size=tamanho)
    return ImageFont.load_default(size=tamanho)


# --------------------------------------------------------------------------- dados


@dataclass
class Medico:
    nome: str
    crm: str
    uf: str
    local: str
    cnes: str
    endereco: str
    bairro: str
    cidade: str
    telefone: str


@dataclass
class Atestado:
    paciente: str
    documento: str
    dias: int
    inicio: str
    fim: str
    cid: str | None
    observacoes: str
    emissao: str
    medico: Medico






@dataclass
class Resultado:
    protocolo: str
    requerente: str
    documento: str
    tipo_avaliacao: str
    data_avaliacao: str
    desfecho: str
    periodo_inicio: str | None
    periodo_fim: str | None
    fundamentacao: str
    emissao: str
    medico: Medico




MEDICOS = [
    Medico("Helena Vasconcelos Prado", "999001", "SP", "Clinica Sinteticas Sao Paulo", "9999001",
           "Rua das Figueiras Falsas, 1200", "Vila Exemplo", "Sao Paulo", "(11) 5555-0101"),
    Medico("Rogério Aparecido Tanaka", "999042", "SP", "Ambulatorio Modelo Zona Sul", "9999042",
           "Avenida dos Testes, 45", "Jardim Amostra", "Sao Paulo", "(11) 5555-0142"),
    Medico("Luís Otávio Mendonça Sá", "999317", "MG", "Centro Medico Fictus", "9999317",
           "Rua Sem Numero, 87", "Bairro Simulado", "Belo Horizonte", "(31) 5555-0317"),
]

POR_EXTENSO = {1: "um", 2: "dois", 3: "tres", 5: "cinco", 7: "sete", 10: "dez", 15: "quinze", 30: "trinta"}


# --------------------------------------------------------------------------- pdf


def _quebrar(c: canvas.Canvas, texto: str, larg: float, fonte="Helvetica", tam=11) -> list[str]:
    c.setFont(fonte, tam)
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if c.stringWidth(teste, fonte, tam) <= larg:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _cabecalho(c: canvas.Canvas, titulo: str, versao: str) -> float:
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(1.2)
    c.line(MARGEM, ALT - 15 * mm, LARG - MARGEM, ALT - 15 * mm)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(LARG / 2, ALT - 28 * mm, titulo)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(LARG / 2, ALT - 33 * mm, versao)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(0.6)
    c.line(MARGEM, ALT - 37 * mm, LARG - MARGEM, ALT - 37 * mm)
    return ALT - 50 * mm


def _bloco_medico(c: canvas.Canvas, m: Medico, emissao: str, y: float) -> float:
    c.setLineWidth(0.4)
    c.line(MARGEM, y + 6 * mm, LARG - MARGEM, y + 6 * mm)
    linhas = [
        f"NOME DO(A) MEDICO(A): {m.nome}          CRM: {m.crm}     UF: {m.uf}",
        f"LOCAL DE ATENDIMENTO: {m.local}          CNES: {m.cnes}",
        f"ENDERECO: {m.endereco}          BAIRRO: {m.bairro}",
        f"CIDADE: {m.cidade}     UF: {m.uf}     TELEFONE: {m.telefone}",
        f"DATA DE EMISSAO: {emissao}",
    ]
    c.setFont("Helvetica", 9)
    for linha in linhas:
        c.drawString(MARGEM, y, linha)
        y -= 5.5 * mm
    return y


def _assinatura(c: canvas.Canvas, y: float) -> None:
    c.setLineWidth(0.6)
    c.line(LARG / 2 - 45 * mm, y, LARG / 2 + 45 * mm, y)
    c.setFont("Helvetica", 9)
    c.drawCentredString(LARG / 2, y - 5 * mm, "ASSINATURA MEDICO(A)")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(LARG / 2, y - 13 * mm, "VIA DIGITAL")
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawCentredString(LARG / 2, y - 18 * mm, VALIDACAO)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(0.65, 0.1, 0.1)
    c.drawCentredString(LARG / 2, 12 * mm, MARCA)
    c.setFillColorRGB(0, 0, 0)


def pdf_atestado(a: Atestado, destino: Path, paginas_extra: int = 0) -> None:
    c = canvas.Canvas(str(destino), pagesize=A4)
    y = _cabecalho(c, "ATESTADO MEDICO", "VERSAO 2.0 | ABRIL DE 2020")

    corpo = (
        f"Atesto que o(a) Sr.(a) {a.paciente}, portador(a) do documento {a.documento}, "
        f"necessita de afastamento de suas atividades laborais por {a.dias} "
        f"({POR_EXTENSO.get(a.dias, a.dias)}) dias, a partir de {a.inicio}, "
        f"encerrando-se em {a.fim}."
    )
    for linha in _quebrar(c, corpo, LARG - 2 * MARGEM, tam=11):
        c.setFont("Helvetica", 11)
        c.drawString(MARGEM, y, linha)
        y -= 6.5 * mm

    y -= 4 * mm
    if a.cid:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGEM, y, f"CID: {a.cid}")
        y -= 8 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEM, y, "OBSERVACOES:")
    y -= 6 * mm
    for linha in _quebrar(c, a.observacoes, LARG - 2 * MARGEM, tam=10):
        c.setFont("Helvetica", 10)
        c.drawString(MARGEM, y, linha)
        y -= 5.5 * mm

    y = _bloco_medico(c, a.medico, a.emissao, ALT - 150 * mm)
    _assinatura(c, y - 25 * mm)

    for i in range(paginas_extra):
        c.showPage()
        y2 = _cabecalho(c, "ANEXO AO ATESTADO", f"PAGINA {i + 2}")
        c.setFont("Helvetica", 10)
        for linha in _quebrar(
            c,
            "Comprovante de comparecimento emitido pela unidade de atendimento, "
            "anexado ao atestado no mesmo arquivo. Este anexo existe para exercitar "
            "documento de mais de uma pagina no mesmo PDF.",
            LARG - 2 * MARGEM,
            tam=10,
        ):
            c.drawString(MARGEM, y2, linha)
            y2 -= 5.5 * mm
        _assinatura(c, 80 * mm)
    c.save()




TIPOS_EXAME = ["Admissional", "Periodico", "Retorno ao trabalho",
               "Mudanca de riscos ocupacionais", "Demissional"]




TIPOS_AVALIACAO = ["Avaliacao inicial", "Prorrogacao", "Recurso"]
DESFECHOS = ["Deferido", "Indeferido"]


def pdf_resultado(r: Resultado, destino: Path) -> None:
    c = canvas.Canvas(str(destino), pagesize=A4)
    y = _cabecalho(c, "RESULTADO DE AVALIACAO MEDICA", "DOCUMENTO DE DECISAO | VERSAO 1.0")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEM, y, "PROTOCOLO:")
    c.setFont("Helvetica", 10)
    c.drawString(MARGEM + 27 * mm, y, r.protocolo)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LARG - MARGEM - 70 * mm, y, "DATA DA AVALIACAO:")
    c.setFont("Helvetica", 10)
    c.drawString(LARG - MARGEM - 26 * mm, y, r.data_avaliacao)
    y -= 9 * mm

    c.setLineWidth(0.4)
    c.line(MARGEM, y + 3 * mm, LARG - MARGEM, y + 3 * mm)
    for rotulo, valor, larg in [("REQUERENTE:", r.requerente, 26),
                                ("DOCUMENTO:", r.documento, 25)]:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGEM, y, rotulo)
        c.setFont("Helvetica", 9)
        c.drawString(MARGEM + larg * mm, y, valor)
        y -= 6 * mm

    y -= 3 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGEM, y, "TIPO DE AVALIACAO:")
    x = MARGEM + 36 * mm
    for tipo in TIPOS_AVALIACAO:
        c.rect(x, y - 0.8 * mm, 3 * mm, 3 * mm, stroke=1, fill=0)
        if tipo == r.tipo_avaliacao:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 0.55 * mm, y - 0.1 * mm, "X")
        c.setFont("Helvetica", 8)
        c.drawString(x + 4.5 * mm, y, tipo)
        x += (len(tipo) * 1.5 + 12) * mm
    y -= 12 * mm

    c.setLineWidth(1.0)
    c.rect(MARGEM, y - 6 * mm, LARG - 2 * MARGEM, 14 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGEM + 5 * mm, y, f"DESFECHO: {r.desfecho.upper()}")
    y -= 18 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEM, y, "PERIODO CONCEDIDO:")
    c.setFont("Helvetica", 10)
    if r.periodo_inicio and r.periodo_fim:
        c.drawString(MARGEM + 42 * mm, y, f"de {r.periodo_inicio} a {r.periodo_fim}")
    else:
        c.drawString(MARGEM + 42 * mm, y, "nao se aplica")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEM, y, "FUNDAMENTACAO:")
    y -= 6 * mm
    for linha in _quebrar(c, r.fundamentacao, LARG - 2 * MARGEM, tam=10):
        c.setFont("Helvetica", 10)
        c.drawString(MARGEM, y, linha)
        y -= 5.5 * mm

    y = _bloco_medico(c, r.medico, r.emissao, ALT - 185 * mm)
    _assinatura(c, y - 20 * mm)
    c.save()




# --------------------------------------------------------------------- degradacoes


def rasterizar(pdf: Path, dpi: int = 150, pagina: int = 0) -> Image.Image:
    doc = pdfium.PdfDocument(str(pdf))
    img = doc[pagina].render(scale=dpi / 72).to_pil().convert("RGB")
    doc.close()
    return img


def ruido_scanner(img: Image.Image, intensidade: float = 9.0) -> Image.Image:
    arr = np.asarray(img).astype(np.float32)
    arr += np.random.normal(0, intensidade, arr.shape)
    arr = np.clip(arr, 0, 255)
    out = Image.fromarray(arr.astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(0.4))


def inclinar(img: Image.Image, graus: float) -> Image.Image:
    return img.rotate(graus, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))


def perspectiva(img: Image.Image, forca: float = 0.045) -> Image.Image:
    """Inclinacao de foto tirada a mao, com Pillow e numpy.

    Sem opencv de proposito: `docs/stack.md` recusa a dependencia, e o `Image.PERSPECTIVE` do Pillow
    faz o mesmo assim que os oito coeficientes sao resolvidos. Pillow mapeia destino para origem,
    entao os pares de pontos entram na ordem inversa da intuitiva.
    """
    w, h = img.size
    d = forca * w
    origem = [(0, 0), (w, 0), (w, h), (0, h)]
    destino = [
        (d * 0.9, d * 0.4), (w - d * 0.3, d * 1.3), (w - d * 1.1, h - d * 0.5), (d * 0.4, h - d * 1.2)
    ]
    linhas = []
    for (xd, yd), (xo, yo) in zip(destino, origem, strict=True):
        linhas.append([xd, yd, 1, 0, 0, 0, -xo * xd, -xo * yd])
        linhas.append([0, 0, 0, xd, yd, 1, -yo * xd, -yo * yd])
    coeficientes = np.linalg.solve(
        np.array(linhas, dtype=np.float64),
        np.array([c for ponto in origem for c in ponto], dtype=np.float64),
    )
    return img.convert("RGB").transform(
        (w, h), Image.PERSPECTIVE, tuple(coeficientes), Image.BICUBIC, fillcolor=(245, 245, 243)
    )


def sombra(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    gx = np.linspace(0.62, 1.04, w)
    gy = np.linspace(1.02, 0.78, h)
    mascara = np.outer(gy, gx)[:, :, None]
    return Image.fromarray(np.clip(arr * mascara, 0, 255).astype(np.uint8))


def captura_de_tela(img: Image.Image) -> Image.Image:
    corte = img.crop((0, 0, img.size[0], int(img.size[1] * 0.58)))
    largura = corte.size[0]
    barra = 44
    tela = Image.new("RGB", (largura, corte.size[1] + barra), (238, 240, 243))
    d = ImageDraw.Draw(tela)
    d.rectangle([0, 0, largura, barra], fill=(226, 229, 234))
    tipografia = fonte_disponivel(18)
    d.text((16, barra // 2), "visualizador de anexos - atestado.pdf", font=tipografia, fill=(70, 75, 85), anchor="lm")
    tela.paste(corte, (0, barra))
    return tela


# ------------------------------------------------------------------------ gabarito


@dataclass
class Caso:
    arquivo: str
    tipo_documento: str
    formato: str
    dificuldade: str
    resultado_esperado: str
    campos: dict
    notas: list[str] = field(default_factory=list)


def gabarito_atestado(a: Atestado, arquivo: str, formato: str, dificuldade: str, notas=()) -> Caso:
    return Caso(
        arquivo=arquivo,
        tipo_documento="atestado_medico",
        formato=formato,
        dificuldade=dificuldade,
        resultado_esperado="extracao_completa",
        campos={
            "paciente_nome": a.paciente,
            "paciente_documento": a.documento,
            "periodo_afastamento": {"inicio": a.inicio, "fim": a.fim, "dias": a.dias},
            "cid": a.cid,
            "medico_nome": a.medico.nome,
            "crm": {"numero": a.medico.crm, "uf": a.medico.uf},
            "cnes": a.medico.cnes,
            "data_emissao": a.emissao,
        },
        notas=list(notas),
    )


# ---------------------------------------------------------------------------- main


# O gerador produz o conjunto inteiro, porque varios arquivos sao derivados de outros, mas o
# repositorio publica apenas os abaixo. Cada um prova uma coisa que nenhum outro prova; o resto era
# variacao de formato que so aumentava o peso do repositorio e o tempo da suite. Documento novo aqui
# obriga a rodar `make cassettes` em seguida, porque o cassete e indexado pelo hash da pagina.
PUBLICADOS = {
    "atestado_01_pdf_nativo.pdf",  # caminho feliz, camada de texto, OCR nao e chamado
    "atestado_02_pdf_digitalizado.pdf",  # mesmo formato, rota OCR: a extensao nao decide
    "atestado_06_captura_tela.png",  # extracao parcial, campo ausente e qualidade marginal
    "atestado_07_foto.heic",  # conversao HEIC para JPEG
    "atestado_08_duas_paginas.pdf",  # rasterizacao pagina a pagina
    "resultado_01_pdf_nativo.pdf",  # segundo tipo, deferido com periodo concedido
    "resultado_02_indeferido_digitalizado.jpg",  # segundo tipo, indeferido sem periodo
}


def main(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    casos: list[Caso] = []

    a1 = Atestado("Ana Beatriz Marques da Silva", "000.000.000-00", 3, "14/09/2026", "16/09/2026",
                  "M54.5", "Repouso relativo e retorno a avaliacao se houver piora.",
                  "14/09/2026", MEDICOS[0])
    a2 = Atestado("Carlos Eduardo Ferraz Lopes", "000.000.000-00", 15, "01/09/2026", "15/09/2026",
                  None, "Paciente orientado quanto ao retorno gradual as atividades.",
                  "01/09/2026", MEDICOS[1])

    # 1. PDF nativo limpo
    p = saida / "atestado_01_pdf_nativo.pdf"
    pdf_atestado(a1, p)
    casos.append(gabarito_atestado(a1, p.name, "pdf_nativo", "facil",
                                   ["tem camada de texto: nao deve chamar OCR"]))

    # 2. PDF digitalizado, sem camada de texto
    img = ruido_scanner(inclinar(rasterizar(p, 150), -1.4), 8)
    p2 = saida / "atestado_02_pdf_digitalizado.pdf"
    img.convert("RGB").save(p2, "PDF", resolution=150, **PDF_INVARIANTE)
    casos.append(gabarito_atestado(a1, p2.name, "pdf_digitalizado", "media",
                                   ["sem camada de texto: exige OCR", "inclinacao de 1,4 grau"]))

    # Captura de tela. Documento proprio, e nao uma copia do atestado_01: o par 01/02 existe para
    # isolar o formato, e so ele precisa da mesma pessoa. Repetir a mesma pessoa aqui faria o
    # conjunto exercitar extracao de nome sobre duas pessoas em cinco atestados.
    a3 = Atestado("Thaís Nogueira Rebouças", "000.000.000-00", 5, "02/09/2026", "06/09/2026", "J11",
                  "Retorno se houver febre persistente.", "02/09/2026", MEDICOS[1])
    tmp6 = saida / "_tmp_captura.pdf"
    pdf_atestado(a3, tmp6)
    p6 = saida / "atestado_06_captura_tela.png"
    captura_de_tela(rasterizar(tmp6, 150)).save(p6)
    tmp6.unlink()
    c6 = gabarito_atestado(a3, p6.name, "png_captura_tela", "media",
                           ["imagem nitida, mas o documento esta cortado",
                            "bloco do medico ausente: campos de CRM e CNES devem vir nulos"])
    c6.resultado_esperado = "extracao_parcial"
    c6.campos["medico_nome"] = None
    c6.campos["crm"] = None
    c6.campos["cnes"] = None
    c6.campos["data_emissao"] = None
    casos.append(c6)

    # 7. HEIC de iPhone, tambem com documento proprio.
    a4 = Atestado("João Vítor Sampaio Rocha", "000.000.000-00", 2, "10/09/2026", "11/09/2026",
                  "M54", "Afastamento por lombalgia aguda.", "10/09/2026", MEDICOS[2])
    tmp7 = saida / "_tmp_heic.pdf"
    pdf_atestado(a4, tmp7)
    p7 = saida / "atestado_07_foto.heic"
    sombra(perspectiva(ruido_scanner(rasterizar(tmp7, 180), 6))).convert("RGB").save(
        p7, format="HEIF", quality=70
    )
    tmp7.unlink()
    casos.append(gabarito_atestado(a4, p7.name, "heic", "dificil",
                                   ["formato nao aceito pelo Textract: exige conversao no processo"]))

    # 8. PDF de duas paginas
    p8 = saida / "atestado_08_duas_paginas.pdf"
    pdf_atestado(a2, p8, paginas_extra=1)
    casos.append(gabarito_atestado(a2, p8.name, "pdf_nativo_multipagina", "media",
                                   ["duas paginas: a operacao sincrona do Textract le apenas uma",
                                    "afastamento de 15 dias, limite do artigo 60 da Lei 8.213/91",
                                    "sem CID: o campo deve vir nulo, nao inferido"]))

    # 12 a 14. Resultado de avaliacao medica
    res1 = Resultado(
        protocolo="2026-AV-0000123", requerente="Cecília Andrade Peixoto", documento="000.000.000-00",
        tipo_avaliacao="Avaliacao inicial", data_avaliacao="09/09/2026", desfecho="Deferido",
        periodo_inicio="09/09/2026", periodo_fim="08/10/2026",
        fundamentacao=("Avaliacao presencial realizada na data indicada. Quadro compativel com a "
                       "documentacao apresentada, com limitacao funcional temporaria para as atividades "
                       "da funcao. Concedido o periodo acima, com reavaliacao ao termino."),
        emissao="09/09/2026", medico=MEDICOS[2],
    )
    res2 = Resultado(
        protocolo="2026-AV-0000417", requerente="Márcio Aurélio Bezerra", documento="000.000.000-00",
        tipo_avaliacao="Prorrogacao", data_avaliacao="16/09/2026", desfecho="Indeferido",
        periodo_inicio=None, periodo_fim=None,
        fundamentacao=("Nao foram identificados elementos que justifiquem a prorrogacao solicitada. "
                       "Documentacao apresentada nao demonstra agravamento em relacao a avaliacao anterior. "
                       "Requerente orientada quanto ao retorno as atividades."),
        emissao="16/09/2026", medico=MEDICOS[0],
    )

    def gabarito_resultado(r: Resultado, arquivo: str, formato: str, dificuldade: str, notas=()) -> Caso:
        periodo = None
        if r.periodo_inicio and r.periodo_fim:
            periodo = {"inicio": r.periodo_inicio, "fim": r.periodo_fim}
        return Caso(
            arquivo=arquivo, tipo_documento="resultado_avaliacao_medica", formato=formato,
            dificuldade=dificuldade, resultado_esperado="extracao_completa",
            campos={
                "protocolo": r.protocolo,
                "requerente_nome": r.requerente,
                "requerente_documento": r.documento,
                "tipo_avaliacao": r.tipo_avaliacao,
                "data_avaliacao": r.data_avaliacao,
                "desfecho": r.desfecho,
                "periodo_concedido": periodo,
                "medico_nome": r.medico.nome,
                "crm": {"numero": r.medico.crm, "uf": r.medico.uf},
                "data_emissao": r.emissao,
                "cid": None,
            },
            notas=list(notas),
        )

    p_res1 = saida / "resultado_01_pdf_nativo.pdf"
    pdf_resultado(res1, p_res1)
    casos.append(gabarito_resultado(res1, p_res1.name, "pdf_nativo", "facil",
                                    ["desfecho vem de campo categorico em caixa destacada",
                                     "tipo de avaliacao vem de caixa marcada",
                                     "nao tem CID: o campo deve vir nulo"]))

    p_res2 = saida / "resultado_02_indeferido_digitalizado.jpg"
    tmp3 = saida / "_tmp_res2.pdf"
    pdf_resultado(res2, tmp3)
    ruido_scanner(inclinar(rasterizar(tmp3, 150), -1.7), 9).convert("RGB").save(p_res2, "JPEG", quality=82)
    tmp3.unlink()
    casos.append(gabarito_resultado(res2, p_res2.name, "jpeg_digitalizado", "dificil",
                                    ["desfecho indeferido: extrair errado inverte a decisao do fluxo",
                                     "periodo concedido nao se aplica e deve vir nulo, nunca inferido",
                                     "a fundamentacao e negativa, e e o texto que modelo tende a atropelar"]))

    descartados = [c for c in casos if c.arquivo not in PUBLICADOS]
    for c in descartados:
        (saida / c.arquivo).unlink(missing_ok=True)
    casos = [c for c in casos if c.arquivo in PUBLICADOS]
    assert len(casos) == len(PUBLICADOS), sorted(PUBLICADOS - {c.arquivo for c in casos})

    (saida / "gabarito.json").write_text(
        json.dumps([asdict(c) for c in casos], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for c in casos:
        print(f"{c.arquivo:42s} {c.tipo_documento:18s} {c.formato:24s} {c.dificuldade}")
    print(f"\n{len(casos)} casos publicados em {saida}, {len(descartados)} gerados e descartados")
    print("Os dublês montam o indice a partir destes arquivos e do gabarito, em memoria.")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
