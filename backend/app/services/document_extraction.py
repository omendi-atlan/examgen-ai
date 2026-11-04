"""Bounded deterministic extraction with page, slide and paragraph provenance."""

from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from docx import Document as WordDocument
from pptx import Presentation
from pypdf import PdfReader

from app.core.config import get_settings

PARSER_VERSION = "1.1.0"
CHUNK_CHARACTERS = 4000
MAX_PRESENTATION_SLIDES = 500


@dataclass(frozen=True)
class ExtractedSegment:
    locator: str
    text: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class ExtractionResult:
    parser_name: str
    parser_version: str
    segments: list[ExtractedSegment]
    page_count: int | None
    metadata: dict[str, object]
    needs_ocr: bool = False


def _split_text(text: str, locator: str, metadata: dict[str, object]) -> list[ExtractedSegment]:
    clean = text.strip()
    if not clean:
        return []
    segments = []
    for start in range(0, len(clean), CHUNK_CHARACTERS):
        end = min(start + CHUNK_CHARACTERS, len(clean))
        segments.append(
            ExtractedSegment(
                locator=f"{locator}:chars-{start + 1}-{end}",
                text=clean[start:end],
                metadata={**metadata, "start_char": start, "end_char": end},
            )
        )
    return segments


def _enforce_character_budget(total: int) -> None:
    if total > get_settings().max_extracted_characters:
        raise ValueError("Document exceeds the configured extracted-character limit.")


def extract_document(
    path: Path, extension: str, *, enable_ocr: bool = False
) -> ExtractionResult:
    """Extract source text under explicit CPU, memory and output-size limits."""
    settings = get_settings()
    if extension == ".pdf":
        reader = PdfReader(path, strict=True)
        page_count = len(reader.pages)
        if page_count > settings.max_pdf_pages:
            raise ValueError("PDF exceeds the configured page-count limit.")
        segments = []
        ocr_pages = []
        ocr_unavailable = False
        pdfium_document = None
        total_characters = 0
        try:
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if not page_text.strip() and enable_ocr:
                    try:
                        import pypdfium2 as pdfium
                        import pytesseract

                        if pdfium_document is None:
                            pdfium_document = pdfium.PdfDocument(str(path))
                        pdfium_page = pdfium_document[page_number - 1]
                        width, height = pdfium_page.get_size()
                        scale = min(
                            2.0,
                            sqrt(settings.max_pdf_page_pixels / max(width * height, 1)),
                        )
                        bitmap = pdfium_page.render(scale=scale)
                        try:
                            page_text = pytesseract.image_to_string(
                                bitmap.to_pil(),
                                timeout=settings.ocr_page_timeout_seconds,
                            )
                        finally:
                            bitmap.close()
                        if page_text.strip():
                            ocr_pages.append(page_number)
                    except (ImportError, OSError, RuntimeError, ValueError):
                        ocr_unavailable = True
                total_characters += len(page_text)
                _enforce_character_budget(total_characters)
                segments.extend(
                    _split_text(
                        page_text,
                        f"page-{page_number}",
                        {
                            "page": page_number,
                            "extraction_method": (
                                "ocr" if page_number in ocr_pages else "text_layer"
                            ),
                        },
                    )
                )
        finally:
            if pdfium_document is not None:
                pdfium_document.close()
        return ExtractionResult(
            parser_name="pypdf+pytesseract" if ocr_pages else "pypdf",
            parser_version=PARSER_VERSION,
            segments=segments,
            page_count=page_count,
            metadata={
                "format": "pdf",
                "metadata": {str(k): str(v) for k, v in (reader.metadata or {}).items()},
                "ocr": {
                    "performed": bool(ocr_pages),
                    "pages": ocr_pages,
                    "available": not ocr_unavailable,
                },
            },
            needs_ocr=ocr_unavailable or not any(segment.text.strip() for segment in segments),
        )

    if extension == ".docx":
        document = WordDocument(path)
        segments = []
        total_characters = 0
        for index, paragraph in enumerate(document.paragraphs, start=1):
            total_characters += len(paragraph.text)
            _enforce_character_budget(total_characters)
            segments.extend(
                _split_text(paragraph.text, f"paragraph-{index}", {"paragraph": index})
            )
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
                total_characters += len(row_text)
                _enforce_character_budget(total_characters)
                segments.extend(
                    _split_text(
                        row_text,
                        f"table-{table_index}-row-{row_index}",
                        {"table": table_index, "row": row_index},
                    )
                )
        return ExtractionResult(
            parser_name="python-docx",
            parser_version="1.x-compatible",
            segments=segments,
            page_count=None,
            metadata={
                "format": "docx",
                "paragraph_count": len(document.paragraphs),
                "table_count": len(document.tables),
            },
        )

    if extension == ".pptx":
        presentation = Presentation(path)
        if len(presentation.slides) > MAX_PRESENTATION_SLIDES:
            raise ValueError("PowerPoint exceeds the configured slide-count limit.")
        segments = []
        total_characters = 0
        for slide_number, slide in enumerate(presentation.slides, start=1):
            for shape_number, shape in enumerate(slide.shapes, start=1):
                if getattr(shape, "has_text_frame", False):
                    total_characters += len(shape.text)
                    _enforce_character_budget(total_characters)
                    segments.extend(
                        _split_text(
                            shape.text,
                            f"slide-{slide_number}-shape-{shape_number}",
                            {"slide": slide_number, "shape": shape_number},
                        )
                    )
                if getattr(shape, "has_table", False):
                    for row_number, row in enumerate(shape.table.rows, start=1):
                        row_text = " | ".join(cell.text.strip() for cell in row.cells)
                        total_characters += len(row_text)
                        _enforce_character_budget(total_characters)
                        segments.extend(
                            _split_text(
                                row_text,
                                f"slide-{slide_number}-table-row-{row_number}",
                                {"slide": slide_number, "table_row": row_number},
                            )
                        )
        return ExtractionResult(
            parser_name="python-pptx",
            parser_version="1.x-compatible",
            segments=segments,
            page_count=len(presentation.slides),
            metadata={"format": "pptx", "slide_count": len(presentation.slides)},
        )

    if extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8")
        _enforce_character_budget(len(text))
        segments = _split_text(text, "text", {"format": extension[1:]})
        return ExtractionResult(
            parser_name="utf-8-text",
            parser_version=PARSER_VERSION,
            segments=segments,
            page_count=None,
            metadata={"format": extension[1:], "encoding": "utf-8"},
        )

    raise ValueError("No extraction parser is registered for this file format.")
