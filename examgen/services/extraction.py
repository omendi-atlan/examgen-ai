"""Academic document extraction.

Turns an uploaded file into structured :class:`ExtractedContent` chunks while
preserving the original file untouched on disk. Every chunk keeps a source
locator (page/sheet/slide) so question generation can cite provenance.

Supported: PDF, DOCX, PPTX, XLSX, CSV, plain text/markdown, HTML, images
(OCR when ``pytesseract`` + the ``tesseract`` binary are available, otherwise a
metadata placeholder is recorded — content is never invented).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".tex", ".log", ".json", ".xml"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
SUPPORTED_EXTENSIONS = (
    {".pdf", ".docx", ".pptx", ".xlsx", ".csv"}
    | TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | IMAGE_EXTENSIONS
)

_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+\S|chapter\s+\d+|unit\s+\d+|section\s+\d+"
    r"|topic\s+\d+|[A-Z][A-Z0-9 \-_]{6,})$",
    re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"(\b[a-zA-Z]\s*=\s*[^=\n]{1,60}|[∑∫√πΔλμθ]|"
    r"\b(?:sin|cos|tan|log|ln|derivative|integral)\b)", re.IGNORECASE)
_TABLE_RE = re.compile(r"(\|.+\||\t.+|\s{3,}\S+\s{3,}\S+)")


@dataclass
class ExtractedChunk:
    heading: str
    kind: str
    text: str
    page: int = 0
    meta: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    chunks: list[ExtractedChunk]
    page_count: int
    total_chars: int
    status: str = "ok"
    notes: str = ""


def _classify(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "paragraph"
    if _HEADING_RE.match(stripped) and len(stripped) < 160:
        return "heading"
    if _FORMULA_RE.search(stripped):
        return "formula"
    if _TABLE_RE.search(stripped):
        return "table"
    if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]\s", stripped):
        return "list"
    return "paragraph"


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(path: Path) -> ExtractionResult:
    from pypdf import PdfReader

    chunks: list[ExtractedChunk] = []
    reader = PdfReader(str(path))
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - malformed page
            chunks.append(ExtractedChunk("", "note", f"[page {page_no} unreadable: {exc}]", page_no))
            continue
        for block in _clean(raw).split("\n\n"):
            block = block.strip()
            if block:
                chunks.append(ExtractedChunk("", _classify(block), block, page_no))
    return ExtractionResult(chunks, len(reader.pages), sum(len(c.text) for c in chunks))


def _extract_docx(path: Path) -> ExtractionResult:
    import docx

    document = docx.Document(str(path))
    chunks: list[ExtractedChunk] = []
    current_heading = ""
    for para in document.paragraphs:
        text = _clean(para.text)
        if not text:
            continue
        style = (para.style.name or "").lower() if para.style else ""
        if "heading" in style or "title" in style:
            current_heading = text
            chunks.append(ExtractedChunk(text, "heading", text))
        else:
            chunks.append(ExtractedChunk(current_heading, _classify(text), text))
    for t_index, table in enumerate(document.tables, start=1):
        rows = [" | ".join(_clean(c.text) for c in row.cells) for row in table.rows]
        body = "\n".join(r for r in rows if r.strip())
        if body:
            chunks.append(ExtractedChunk(
                current_heading, "table", body, meta={"table": t_index}))
    return ExtractionResult(chunks, 1, sum(len(c.text) for c in chunks))


def _extract_pptx(path: Path) -> ExtractionResult:
    from pptx import Presentation

    prs = Presentation(str(path))
    chunks: list[ExtractedChunk] = []
    for slide_no, slide in enumerate(prs.slides, start=1):
        title = ""
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = _clean(shape.text_frame.text)
            if not text:
                continue
            is_title = getattr(shape, "is_placeholder", False) and shape.placeholder_format.idx == 0
            if is_title and not title:
                title = text
                chunks.append(ExtractedChunk(title, "heading", text, slide_no))
            else:
                for block in text.split("\n\n"):
                    block = block.strip()
                    if block:
                        chunks.append(ExtractedChunk(title, _classify(block), block, slide_no))
    return ExtractionResult(chunks, len(prs.slides._sldIdLst), sum(len(c.text) for c in chunks))


def _extract_xlsx(path: Path) -> ExtractionResult:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), data_only=True, read_only=True)
    chunks: list[ExtractedChunk] = []
    for sheet in wb.worksheets:
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            body = "\n".join(rows[:500])
            chunks.append(ExtractedChunk(
                sheet.title, "table", body, meta={"sheet": sheet.title, "rows": len(rows)}))
    wb.close()
    return ExtractionResult(chunks, len(wb.sheetnames), sum(len(c.text) for c in chunks))


def _extract_csv(path: Path) -> ExtractionResult:
    raw = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(raw))
    rows = [" | ".join(r) for r in reader if any(c.strip() for c in r)]
    body = "\n".join(rows[:500])
    chunks = [ExtractedChunk(path.stem, "table", body)] if body else []
    return ExtractionResult(chunks, 1, sum(len(c.text) for c in chunks))


def _extract_text(path: Path) -> ExtractionResult:
    raw = _clean(path.read_text(encoding="utf-8", errors="replace"))
    chunks: list[ExtractedChunk] = []
    heading = ""
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        kind = _classify(block)
        if kind == "heading":
            heading = block
        chunks.append(ExtractedChunk(heading, kind, block))
    return ExtractionResult(chunks, 1, sum(len(c.text) for c in chunks))


def _extract_html(path: Path) -> ExtractionResult:
    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in {"script", "style"}:
                self._skip = True

        def handle_endtag(self, tag):
            if tag in {"script", "style"}:
                self._skip = False

        def handle_data(self, data):
            if not self._skip and data.strip():
                self.parts.append(data.strip())

    collector = _Collector()
    collector.feed(path.read_text(encoding="utf-8", errors="replace"))
    text = _clean("\n\n".join(collector.parts))
    chunks = [ExtractedChunk("", _classify(b), b)
              for b in text.split("\n\n") if b.strip()]
    return ExtractionResult(chunks, 1, sum(len(c.text) for c in chunks))


def _extract_image(path: Path) -> ExtractionResult:
    from PIL import Image

    notes = ""
    try:
        with Image.open(path) as img:
            width, height = img.size
            meta = {"width": width, "height": height, "format": img.format or ""}
    except Exception as exc:  # pragma: no cover - corrupt image
        return ExtractionResult([], 0, 0, "error", f"Unreadable image: {exc}")

    ocr_text = ""
    try:
        import pytesseract  # type: ignore

        ocr_text = _clean(pytesseract.image_to_string(str(path)))
    except Exception:
        notes = ("OCR engine unavailable; image stored as an asset. "
                 "Install pytesseract + tesseract for text recognition.")

    chunks: list[ExtractedChunk] = []
    if ocr_text:
        chunks = [ExtractedChunk("", _classify(b), b) for b in ocr_text.split("\n\n") if b.strip()]
    else:
        chunks = [ExtractedChunk(
            "", "image", f"[Image asset: {path.name}]", meta=meta)]
    return ExtractionResult(chunks, 1, sum(len(c.text) for c in chunks),
                            "warning" if not ocr_text else "ok", notes)


_EXTRACTORS = {
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".pptx": _extract_pptx,
    ".xlsx": _extract_xlsx,
    ".csv": _extract_csv,
}


def extract(path: Path) -> ExtractionResult:
    """Extract structured content from a supported document."""
    ext = path.suffix.lower()
    if ext in _EXTRACTORS:
        try:
            return _EXTRACTORS[ext](path)
        except Exception as exc:  # pragma: no cover - defensive
            return ExtractionResult([], 0, 0, "error", f"Extraction failed: {exc}")
    if ext in HTML_EXTENSIONS:
        try:
            return _extract_html(path)
        except Exception as exc:  # pragma: no cover
            return ExtractionResult([], 0, 0, "error", f"Extraction failed: {exc}")
    if ext in TEXT_EXTENSIONS:
        try:
            return _extract_text(path)
        except Exception as exc:  # pragma: no cover
            return ExtractionResult([], 0, 0, "error", f"Extraction failed: {exc}")
    if ext in IMAGE_EXTENSIONS:
        return _extract_image(path)
    return ExtractionResult([], 0, 0, "error", f"Unsupported file type: {ext or 'unknown'}")


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS
