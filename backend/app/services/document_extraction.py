"""Deterministic text extraction with page, slide and paragraph provenance."""

from dataclasses import dataclass
from pathlib import Path

from docx import Document as WordDocument
from pptx import Presentation
from pypdf import PdfReader

PARSER_VERSION = "1.0.0"
CHUNK_CHARACTERS = 4000


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


def extract_document(path: Path, extension: str) -> ExtractionResult:
    """Extract source text while preserving stable structural locators."""
    if extension == ".pdf":
        reader = PdfReader(path, strict=True)
        segments = []
        for page_number, page in enumerate(reader.pages, start=1):
            segments.extend(
                _split_text(page.extract_text() or "", f"page-{page_number}", {"page": page_number})
            )
        return ExtractionResult(
            parser_name="pypdf",
            parser_version="5.x-compatible",
            segments=segments,
            page_count=len(reader.pages),
            metadata={"format": "pdf", "metadata": {str(k): str(v) for k, v in (reader.metadata or {}).items()}},
            needs_ocr=not any(segment.text.strip() for segment in segments),
        )

    if extension == ".docx":
        document = WordDocument(path)
        segments = []
        for index, paragraph in enumerate(document.paragraphs, start=1):
            segments.extend(_split_text(paragraph.text, f"paragraph-{index}", {"paragraph": index}))
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
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
            metadata={"format": "docx", "paragraph_count": len(document.paragraphs), "table_count": len(document.tables)},
        )

    if extension == ".pptx":
        presentation = Presentation(path)
        segments = []
        for slide_number, slide in enumerate(presentation.slides, start=1):
            for shape_number, shape in enumerate(slide.shapes, start=1):
                if getattr(shape, "has_text_frame", False):
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
        segments = _split_text(text, "text", {"format": extension[1:]})
        return ExtractionResult(
            parser_name="utf-8-text",
            parser_version="1.0.0",
            segments=segments,
            page_count=None,
            metadata={"format": extension[1:], "encoding": "utf-8"},
        )

    raise ValueError("No extraction parser is registered for this file format.")
