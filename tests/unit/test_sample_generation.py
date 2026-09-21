"""The synthetic sample generator keeps cassette keys stable across runs."""

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_the_synthetic_generator_is_deterministic() -> None:
    """Os documentos não são versionados, então regerar precisa dar exatamente os mesmos bytes.

    Se não desse, todo cassete erraria: a chave do cassete é o hash da página renderizada. Duas
    fontes de não determinismo já foram encontradas e fechadas aqui — o `CreationDate` do reportlab
    e o do escritor de PDF do Pillow — e este teste impede a terceira de passar despercebida.

    Gera um PDF duas vezes em vez do conjunto inteiro: o conjunto leva alguns segundos, e o que
    precisa ser guardado é a propriedade, não o tempo de suíte.
    """
    import sys

    sys.path.insert(0, str(ROOT / "samples"))
    try:
        gerador = importlib.import_module("gerar_sinteticos")
    except ModuleNotFoundError:  # pragma: no cover - grupo `samples` ausente
        pytest.skip("grupo de dependências `samples` não instalado")
    finally:
        sys.path.pop(0)

    atestado = gerador.Atestado(
        "Ana Beatriz Marques da Silva",
        "000.000.000-00",
        3,
        "14/09/2026",
        "16/09/2026",
        "M54.5",
        "Repouso relativo.",
        "14/09/2026",
        gerador.MEDICOS[0],
    )

    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        primeiro, segundo = Path(pasta) / "a.pdf", Path(pasta) / "b.pdf"
        gerador.pdf_atestado(atestado, primeiro)
        gerador.pdf_atestado(atestado, segundo)

        assert primeiro.read_bytes() == segundo.read_bytes()
