import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_the_synthetic_generator_is_deterministic() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "samples"))
    try:
        generator = importlib.import_module("generate_synthetic_samples")
    except ModuleNotFoundError:  # pragma: no cover
        pytest.skip("grupo de dependências `samples` não instalado")
    finally:
        sys.path.pop(0)

    certificate = generator.Certificate(
        "Ana Beatriz Marques da Silva",
        "000.000.000-00",
        3,
        "14/09/2026",
        "16/09/2026",
        "M54.5",
        "Repouso relativo.",
        "14/09/2026",
        generator.DOCTORS[0],
    )

    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        first, second = Path(folder) / "a.pdf", Path(folder) / "b.pdf"
        generator.generate_certificate_pdf(certificate, first)
        generator.generate_certificate_pdf(certificate, second)

        assert first.read_bytes() == second.read_bytes()
