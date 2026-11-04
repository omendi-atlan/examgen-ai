"""Resource-bound extraction regression tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import document_extraction
from pptx import Presentation
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


def test_pptx_extraction_retains_slide_and_shape_citation_locators(tmp_path: Path) -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(0, 0, 5000000, 1000000)
    shape.text = "Learning outcome: explain relational database normalization."
    source = tmp_path / "module-outline.pptx"
    presentation.save(source)

    result = document_extraction.extract_document(source, ".pptx")

    assert result.page_count == 1
    assert result.segments[0].locator == "slide-1-shape-1:chars-1-60"
    assert result.segments[0].metadata == {"slide": 1, "shape": 1, "start_char": 0, "end_char": 60}


def test_concurrent_representative_text_extraction_preserves_all_source_chunks(
    tmp_path: Path,
) -> None:
    sources = []
    expected_characters = 256_000
    for index in range(4):
        source = tmp_path / f"module-{index}.txt"
        source.write_text("A" * expected_characters, encoding="utf-8")
        sources.append(source)

    def extract(source: Path):
        return document_extraction.extract_document(source, ".txt")

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(extract, sources))

    assert len(results) == 4
    for result in results:
        assert sum(len(segment.text) for segment in result.segments) == expected_characters
        assert len(result.segments) == 64
        assert result.segments[0].locator == "text:chars-1-4000"
        assert result.segments[-1].locator == "text:chars-253001-256000"
