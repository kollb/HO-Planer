"""Optionale Regressionstests für private Zeitnachweise.

Ausführung nur lokal, beispielsweise unter Windows:
    set HO_PLANER_PDF_FIXTURE_DIR=..\\pdf
    py -m pytest tests/test_private_pdf_regression.py

Optional kann HO_PLANER_PDF_EXPECTATIONS auf ein nicht versioniertes JSON-Manifest
zeigen. Es darf keine PDF-Inhalte oder personenbezogene Daten in Testausgaben schreiben.
"""

import json
import os
from pathlib import Path

import pytest

from app import parse_pdf_content


PDF_DIRECTORY = os.environ.get("HO_PLANER_PDF_FIXTURE_DIR")
EXPECTATIONS_PATH = os.environ.get("HO_PLANER_PDF_EXPECTATIONS")


def _private_pdf_files():
    if not PDF_DIRECTORY:
        pytest.skip("HO_PLANER_PDF_FIXTURE_DIR ist nicht gesetzt.", allow_module_level=True)
    directory = Path(PDF_DIRECTORY)
    if not directory.is_dir():
        pytest.skip("Privater PDF-Ordner ist nicht verfügbar.", allow_module_level=True)
    files = sorted(directory.glob("*.pdf"))
    if not files:
        pytest.skip("Privater PDF-Ordner enthält keine PDFs.", allow_module_level=True)
    return files


def _expectations():
    if not EXPECTATIONS_PATH:
        return {}
    path = Path(EXPECTATIONS_PATH)
    if not path.is_file():
        pytest.fail("HO_PLANER_PDF_EXPECTATIONS verweist nicht auf eine Datei.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("pdf_path", _private_pdf_files(), ids=lambda path: path.name)
def test_private_pdf_parser_regression(pdf_path):
    """Prüft ausschließlich Parserstruktur; es erfolgt kein Import in SQLite."""
    with pdf_path.open("rb") as pdf_file:
        entries, report = parse_pdf_content(pdf_file, include_report=True)

    assert report["recognized_month"], "PDF-Berichtsmonat wurde nicht erkannt."
    assert report["pages"] > 0
    assert report["recognized_rows"] > 0
    assert entries, "PDF enthält keine importierbaren Blöcke."

    expected = _expectations().get(pdf_path.name, {})
    if "recognized_month" in expected:
        assert report["recognized_month"] == expected["recognized_month"]
    if "minimum_entries" in expected:
        assert len(entries) >= expected["minimum_entries"]
