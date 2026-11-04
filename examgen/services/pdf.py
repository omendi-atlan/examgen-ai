"""PDF deliverable generation.

Two independent documents are produced from the *same* examination version:

    PDF 1 — Examination Memorandum and Marking Guide
    PDF 2 — Subject Mastery and Examination Preparation Guide

Both carry the same examination identifier and version so the website, the
memorandum and the mastery guide can never drift apart.

Diagrams are drawn natively with ReportLab canvas primitives (no external
native renderer required), so the PDFs are self-contained and reproducible.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
ACCENT = colors.HexColor("#2563eb")
LINE = colors.HexColor("#cbd5e1")
SOFT = colors.HexColor("#eef2ff")
SOFT2 = colors.HexColor("#ecfdf5")
SOFT3 = colors.HexColor("#fff7ed")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20,
                                textColor=INK, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=10,
                                   textColor=MUTED, alignment=1, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=15,
                             textColor=INK, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5,
                             textColor=ACCENT, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11,
                             textColor=INK, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.6,
                               leading=14, textColor=INK, alignment=TA_JUSTIFY),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8.4,
                                leading=12, textColor=MUTED),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=8.6,
                               textColor=MUTED),
    }


class _Diagram(Flowable):
    """Flowable that draws a diagram from its specification."""

    def __init__(self, spec: dict, width: float, height: float = 150):
        super().__init__()
        self.spec = spec or {}
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):  # noqa: N802
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        canvas = self.canv
        spec = self.spec
        nodes = spec.get("nodes") or [{"label": label} for label in spec.get("labels", [])]
        if not nodes:
            nodes = [{"label": "Component"}]
        title = spec.get("title", "Diagram")
        diagram_type = spec.get("diagram_type", "annotated")
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(INK)
        canvas.drawString(0, self.height - 10, title)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0, self.height - 19,
                          f"{diagram_type.replace('_', ' ')} — version {spec.get('version', 1)}")
        top = self.height - 28
        count = len(nodes)
        if count == 0:
            canvas.restoreState()
            return
        box_h = min(18, max(12, (top - 6) / max(count, 1) - 4))
        for index, node in enumerate(nodes):
            y = top - (index + 1) * (box_h + 5)
            label = str(node.get("label", f"Item {index + 1}"))[:46]
            canvas.setFillColor(SOFT if index % 2 == 0 else SOFT2)
            canvas.setStrokeColor(LINE)
            canvas.roundRect(0, y, self.width * 0.62, box_h, 3, stroke=1, fill=1)
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica", 8)
            canvas.drawString(5, y + box_h / 2 - 2.5, label)
            if index < count - 1:
                canvas.setStrokeColor(MUTED)
                canvas.setLineWidth(0.7)
                canvas.line(self.width * 0.31, y, self.width * 0.31, y - 5)
                canvas.line(self.width * 0.31, y - 5, self.width * 0.31 - 2, y - 3)
                canvas.line(self.width * 0.31, y - 5, self.width * 0.31 + 2, y - 3)
            detail = str(node.get("detail", "") or "")
            if detail:
                canvas.setFillColor(MUTED)
                canvas.setFont("Helvetica-Oblique", 7)
                canvas.drawString(self.width * 0.65, y + box_h / 2 - 2.5, detail[:30])
        canvas.restoreState()


def _header_footer(title: str, subject: str, exam_id: str, version: int):
    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, A4[1] - 12 * mm, f"{subject} — {title}")
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm,
                               f"Exam {exam_id[:12]} · v{version}")
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, 10 * mm, "EXAMGEN AI — generated from student coursework")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return _draw


def _build(path: Path, title: str, subject: str, exam_id: str, version: int, story: list) -> None:
    doc = BaseDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=title, author="EXAMGEN AI",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(
        id="main", frames=[frame],
        onPage=_header_footer(title, subject, exam_id, version))])
    doc.build(story)


def _table(rows: list[list], widths: list[float] | None = None,
           header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    table.setStyle(TableStyle(style))
    return table


def _cover(styles: dict, examination: dict, doc_kind: str, extra_meta: list[tuple[str, str]]) -> list:
    story = [
        Spacer(1, 24 * mm),
        Paragraph(doc_kind, styles["title"]),
        Paragraph(examination.get("title", ""), styles["h2"]),
        Paragraph(f"{examination.get('subject_name', '')}"
                  f"{' · ' + examination.get('module_name') if examination.get('module_name') else ''}",
                  styles["subtitle"]),
        Spacer(1, 6 * mm),
    ]
    rows = [["Field", "Value"]] + [[k, v] for k, v in extra_meta]
    story.append(_table(rows, widths=[55 * mm, 110 * mm]))
    story.append(Spacer(1, 8 * mm))
    return story


def build_memorandum(path: Path, examination: dict, questions: list[dict],
                     visuals: dict[str, dict] | None = None) -> dict:
    """PDF 1 — Examination Memorandum and Marking Guide."""
    styles = _styles()
    visuals = visuals or {}
    total_marks = sum(int(q.get("marks", 0)) for q in questions)
    story = _cover(styles, examination, "Examination Memorandum &amp; Marking Guide", [
        ("Examination ID", examination.get("id", "")),
        ("Version", str(examination.get("version", 1))),
        ("Mode", examination.get("mode", "practice").title()),
        ("Duration", f"{examination.get('duration_minutes', 0)} minutes"),
        ("Total marks", str(total_marks)),
        ("Questions", str(len(questions))),
        ("Moderation status", examination.get("moderation_status", "").replace("_", " ").title()),
        ("Generated", examination.get("generated_at", "")),
    ])
    story.append(Paragraph(
        "This memorandum is the authoritative marking guide for the examination "
        "identified above. Mark objective questions strictly against the keyed answer. "
        "Mark extended responses against the published rubric and award partial credit "
        "only where the rubric permits it.", styles["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Mark allocation summary", styles["h2"]))
    summary_rows = [["#", "Type", "Marks", "Section"]]
    for index, q in enumerate(questions, start=1):
        summary_rows.append([str(index), q.get("qtype", "").replace("_", " ").title(),
                             str(q.get("marks", 0)), q.get("section", "")])
    summary_rows.append(["", "TOTAL", str(total_marks), ""])
    story.append(_table(summary_rows, widths=[12 * mm, 55 * mm, 20 * mm, 70 * mm]))
    story.append(PageBreak())

    for index, q in enumerate(questions, start=1):
        block: list = [Paragraph(f"Question {index}", styles["h1"])]
        block.append(Paragraph(
            f"<b>Type:</b> {q.get('qtype', '').replace('_', ' ').title()} &nbsp;&nbsp; "
            f"<b>Marks:</b> {q.get('marks', 0)} &nbsp;&nbsp; "
            f"<b>Difficulty:</b> {q.get('difficulty', '')} &nbsp;&nbsp; "
            f"<b>Bloom:</b> {q.get('bloom', '')}", styles["meta"]))
        if q.get("topic_name"):
            block.append(Paragraph(f"<b>Topic:</b> {q['topic_name']}", styles["meta"]))
        block.append(Spacer(1, 2 * mm))
        block.append(Paragraph("<b>Question</b>", styles["h3"]))
        block.append(Paragraph(_esc(q.get("prompt", "")).replace("\n", "<br/>"), styles["body"]))
        if q.get("options"):
            block.append(Spacer(1, 1 * mm))
            for label, option in zip("ABCDEFGH", q["options"]):
                block.append(Paragraph(f"({label}) {_esc(str(option))}", styles["body"]))
        visual = visuals.get(q.get("visual_asset_id") or "")
        if visual:
            block.append(Spacer(1, 2 * mm))
            block.append(_Diagram(visual, 160 * mm, 120))
        block.append(Spacer(1, 2 * mm))
        block.append(Paragraph("<b>Model answer</b>", styles["h3"]))
        block.append(Paragraph(_esc(q.get("expected_answer", "")).replace("\n", "<br/>"),
                               styles["body"]))
        if q.get("acceptable_alternatives"):
            block.append(Paragraph(
                "<b>Acceptable alternatives:</b> "
                + "; ".join(_esc(str(a)) for a in q["acceptable_alternatives"]),
                styles["small"]))
        if q.get("rubrics"):
            block.append(Spacer(1, 1.5 * mm))
            block.append(Paragraph("<b>Marking criteria</b>", styles["h3"]))
            rows = [["Criterion", "Marks", "Guidance", "Partial credit"]]
            for rubric in q["rubrics"]:
                rows.append([_esc(str(rubric.get("criterion", ""))), str(rubric.get("marks", "")),
                             _esc(str(rubric.get("guidance", ""))),
                             "Yes" if rubric.get("partial_credit") else "No"])
            block.append(_table(rows, widths=[50 * mm, 15 * mm, 70 * mm, 22 * mm]))
        if q.get("explanation"):
            block.append(Spacer(1, 1.5 * mm))
            block.append(Paragraph(f"<b>Explanation:</b> {_esc(q['explanation'])}", styles["body"]))
        if q.get("common_errors"):
            block.append(Paragraph(
                "<b>Common incorrect responses:</b> "
                + "; ".join(_esc(str(e)) for e in q["common_errors"]), styles["small"]))
        block.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(block[:6]) if len(block) > 6 else block[0])
        story.extend(block[6:] if len(block) > 6 else block[1:])

    _build(path, "Examination Memorandum", examination.get("subject_name", ""),
           examination.get("id", ""), int(examination.get("version", 1)), story)
    return {"path": str(path), "pages_hint": len(story)}


def build_mastery_guide(path: Path, examination: dict, topics: list[dict],
                        questions: list[dict], visuals: dict[str, dict] | None,
                        analytics: dict | None = None,
                        definitions: dict[str, list[str]] | None = None,
                        formulas: dict[str, list[str]] | None = None) -> dict:
    """PDF 2 — Subject Mastery and Examination Preparation Guide."""
    styles = _styles()
    visuals = visuals or {}
    definitions = definitions or {}
    formulas = formulas or {}
    analytics = analytics or {}
    story = _cover(styles, examination, "Subject Mastery &amp; Examination Preparation Guide", [
        ("Subject", examination.get("subject_name", "")),
        ("Module", examination.get("module_name", "")),
        ("Examination ID", examination.get("id", "")),
        ("Version", str(examination.get("version", 1))),
        ("Duration", f"{examination.get('duration_minutes', 0)} minutes"),
        ("Total marks", str(sum(int(q.get("marks", 0)) for q in questions))),
        ("Topics covered", str(len(topics))),
        ("Generated", examination.get("generated_at", "")),
    ])

    # A. Academic orientation
    story.append(Paragraph("A. Academic orientation", styles["h1"]))
    story.append(Paragraph(
        f"This guide prepares you for the examination in "
        f"<b>{_esc(examination.get('subject_name', ''))}</b>"
        + (f" ({_esc(examination.get('module_name', ''))})" if examination.get("module_name") else "")
        + ". Every section is built from the coursework you uploaded for this subject.",
        styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Topics and learning outcomes", styles["h2"]))
    rows = [["Topic", "Coverage", "Learning outcomes identified"]]
    for topic in topics:
        outcomes = topic.get("outcomes") or []
        rows.append([_esc(str(topic.get("name", ""))),
                     str(topic.get("coverage", "")).title(),
                     str(len(outcomes))])
    story.append(_table(rows, widths=[60 * mm, 25 * mm, 72 * mm]))
    story.append(Spacer(1, 2 * mm))
    objectives = examination.get("assessment_objectives") or []
    if objectives:
        story.append(Paragraph("Examination objectives", styles["h2"]))
        for objective in objectives:
            story.append(Paragraph(f"• {_esc(str(objective))}", styles["body"]))

    # B. In-depth subject notes
    story.append(Paragraph("B. In-depth subject notes", styles["h1"]))
    for topic in topics:
        story.append(Paragraph(_esc(str(topic.get("name", ""))), styles["h2"]))
        if topic.get("summary"):
            story.append(Paragraph(_esc(str(topic["summary"])), styles["body"]))
        topic_defs = definitions.get(topic.get("id", "")) or []
        if topic_defs:
            story.append(Paragraph("Key definitions", styles["h3"]))
            for definition in topic_defs:
                story.append(Paragraph(f"• {_esc(str(definition))}", styles["body"]))
        topic_formulas = formulas.get(topic.get("id", "")) or []
        if topic_formulas:
            story.append(Paragraph("Formulas and relationships", styles["h3"]))
            for formula in topic_formulas:
                story.append(Paragraph(f"• {_esc(str(formula))}", styles["body"]))
        if topic.get("key_points"):
            story.append(Paragraph("Core concepts", styles["h3"]))
            for point in topic["key_points"]:
                story.append(Paragraph(f"• {_esc(str(point))}", styles["body"]))
        for subtopic in topic.get("subtopics", []):
            story.append(Paragraph(_esc(str(subtopic.get("name", ""))), styles["h3"]))
            if subtopic.get("summary"):
                story.append(Paragraph(_esc(str(subtopic["summary"])), styles["body"]))
            for outcome in subtopic.get("outcomes", []):
                statement = outcome.get("statement") if isinstance(outcome, dict) else outcome
                story.append(Paragraph(f"– {_esc(str(statement))}", styles["body"]))
        visual_ids = topic.get("visual_ids") or []
        for visual_id in visual_ids:
            visual = visuals.get(visual_id)
            if visual:
                story.append(Spacer(1, 2 * mm))
                story.append(_Diagram(visual, 160 * mm, 120))
                story.append(Paragraph(
                    f"<i>{_esc(str(visual.get('title', '')))}</i> — "
                    f"practise reconstructing this diagram from memory.",
                    styles["small"]))
        story.append(Spacer(1, 3 * mm))

    # C. Examination-focused preparation
    story.append(PageBreak())
    story.append(Paragraph("C. Examination-focused preparation", styles["h1"]))
    story.append(Paragraph(
        "<b>What you must know.</b> The definitions and terminology in Section B. "
        "Objective questions in this paper draw directly on these.", styles["body"]))
    story.append(Paragraph(
        "<b>What you must understand.</b> The relationships between concepts, and why each "
        "process or structure exists — not merely its name.", styles["body"]))
    story.append(Paragraph(
        "<b>What you must apply.</b> Calculation, interpretation and structured-answer "
        "questions require you to use the concepts in unfamiliar contexts.", styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Command words and what they require", styles["h2"]))
    command_rows = [["Command word", "What the examiner expects"]]
    for word, expectation in [
        ("Define", "A precise statement of meaning, using correct terminology."),
        ("Describe", "A factual account of features, stages or characteristics."),
        ("Explain", "Reasons and mechanisms — the ‘why’, not just the ‘what’."),
        ("Calculate", "Working shown, correct units, and a clearly stated answer."),
        ("Compare", "Similarities and differences, explicitly linked."),
        ("Analyse", "Break the topic into parts and examine how they relate."),
        ("Evaluate", "Weigh evidence and reach a justified judgement."),
        ("Discuss", "Balanced treatment of multiple perspectives."),
    ]:
        command_rows.append([word, expectation])
    story.append(_table(command_rows, widths=[35 * mm, 122 * mm]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Frequently misunderstood areas", styles["h2"]))
    misunderstood = []
    for question in questions:
        for error in question.get("common_errors") or []:
            if error not in misunderstood:
                misunderstood.append(error)
    if misunderstood:
        for error in misunderstood[:12]:
            story.append(Paragraph(f"• {_esc(str(error))}", styles["body"]))
    else:
        story.append(Paragraph("No recurring misconceptions were identified from your material.",
                               styles["body"]))

    # D. Memorisation and retention
    story.append(Paragraph("D. Memorisation and retention", styles["h1"]))
    story.append(Paragraph(
        "Use active methods rather than re-reading. Choose the method that matches the "
        "assessment objective — memorisation alone will not earn marks where the paper "
        "requires application or evaluation.", styles["body"]))
    methods = [["Method", "Best used for", "How to apply it"]]
    for method, best_for, how in [
        ("Spaced repetition", "Definitions and terminology",
         "Review at increasing intervals: day 1, 3, 7, 21."),
        ("Flashcards / active recall", "Key facts and formulas",
         "Write the term on one side, the definition on the other; test yourself aloud."),
        ("Process reconstruction", "Procedures and algorithms",
         "Write the steps from memory, then check against your notes."),
        ("Diagram reconstruction", "Visual and structural topics",
         "Redraw each diagram from memory and label it without looking."),
        ("Comparison tables", "Similar or easily confused concepts",
         "Create a table contrasting features, causes or outcomes."),
        ("Worked examples", "Calculations and problem solving",
         "Re-solve examples with the solution hidden, then compare methods."),
    ]:
        methods.append([method, best_for, how])
    story.append(_table(methods, widths=[38 * mm, 45 * mm, 74 * mm]))

    # E. Worked examples
    story.append(Paragraph("E. Worked examples", styles["h1"]))
    worked = [q for q in questions if q.get("qtype") in {"numerical", "formula", "short_answer",
                                                         "extended_response", "essay",
                                                         "case_study", "diagram_interpretation"}]
    if worked:
        for question in worked[:6]:
            story.append(Paragraph(_esc(str(question.get("prompt", ""))[:240]), styles["h3"]))
            story.append(Paragraph(
                "<b>Model response:</b> "
                + _esc(str(question.get("expected_answer", ""))[:700]), styles["body"]))
            if question.get("explanation"):
                story.append(Paragraph(
                    f"<i>{_esc(str(question['explanation'])[:400])}</i>", styles["small"]))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph(
            "No calculation-based material was identified in your uploaded resources.",
            styles["body"]))

    # F. Examination techniques
    story.append(Paragraph("F. Examination techniques", styles["h1"]))
    for tip in [
        "Read the whole paper during the reading time and note the mark value of each question.",
        "Allocate roughly one minute per mark, and never over-run on a single question.",
        "Underline the command word in every question before you begin answering.",
        "Show all calculation steps; method marks are awarded even when the final answer is wrong.",
        "State units in every numerical answer — an unqualified number cannot earn full marks.",
        "For extended answers, plan three or four key points before writing.",
        "Use subject terminology deliberately; examiners award marks for correct vocabulary.",
        "Reserve the last ten percent of the time for checking, especially objective sections.",
    ]:
        story.append(Paragraph(f"• {_esc(tip)}", styles["body"]))

    # G. Personalised revision priorities
    story.append(Paragraph("G. Personalised revision priorities", styles["h1"]))
    recommendations = analytics.get("recommendations") or []
    if analytics.get("attempts"):
        story.append(Paragraph(
            f"Based on {analytics.get('attempts')} marked attempt(s) in this subject, with an "
            f"average of {analytics.get('average_percentage')}%.", styles["body"]))
        weak = [row for row in (analytics.get("by_topic") or []) if row.get("percentage", 100) < 70]
        if weak:
            rows = [["Topic", "Your score", "Mastery", "Priority"]]
            for index, row in enumerate(weak[:10], start=1):
                rows.append([_esc(str(row.get("name", ""))), f"{row.get('percentage')}%",
                             str(row.get("mastery", "")).replace("_", " ").title(),
                             f"#{index}"])
            story.append(_table(rows, widths=[65 * mm, 25 * mm, 40 * mm, 20 * mm]))
        for recommendation in recommendations:
            story.append(Paragraph(f"• {_esc(str(recommendation))}", styles["body"]))
    else:
        story.append(Paragraph(
            "No marked attempts have been recorded for this subject yet. Complete a practice "
            "examination first; this section will then identify your weakest topics and "
            "rank revision priorities using your actual results.", styles["body"]))
        if topics:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Suggested first-pass revision order", styles["h3"]))
            for topic in topics[:8]:
                story.append(Paragraph(f"• {_esc(str(topic.get('name', '')))}", styles["body"]))

    _build(path, "Subject Mastery Guide", examination.get("subject_name", ""),
           examination.get("id", ""), int(examination.get("version", 1)), story)
    return {"path": str(path), "pages_hint": len(story)}


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
