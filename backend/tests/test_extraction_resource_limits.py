"""Resource-bound extraction regression tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import document_extraction
from pypdf import PdfWriter


def test_pdf_page_count_limit_is_enforced_before_page_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "many-pages.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as output:
        writer.write(output)
    monkeypatch.setattr(
        document_extraction,
        "get_settings",
        lambda: SimpleNamespace(max_pdf_pages=1),
    )

    with pytest.raises(ValueError, match="page-count limit"):
        document_extraction.extract_document(source, ".pdf")


def test_text_extraction_character_budget_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "large.txt"
    source.write_text("A" * 101, encoding="utf-8")
    monkeypatch.setattr(
        document_extraction,
        "get_settings",
        lambda: SimpleNamespace(max_extracted_characters=100),
    )

    with pytest.raises(ValueError, match="character limit"):
        document_extraction.extract_document(source, ".txt")
