import json
from pathlib import Path

import pytest

from entrypoints.cli import main

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"


def test_cli_analisar_valid_certificate(capsys: pytest.CaptureFixture[str]) -> None:
    path = str(SAMPLES / "atestado_01_pdf_nativo.pdf")
    exit_code = main(["analisar", path])
    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["document_type"]["value"] == "medical_certificate"
    assert output["fields"]["leave_period"]["value"] == {
        "days": 3,
        "start": "2026-09-14",
        "end": "2026-09-16",
    }


def test_cli_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["analisar", "nonexistent.pdf"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "file not found" in captured.err
