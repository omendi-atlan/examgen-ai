"""Subject assistant — a grounded, workspace-scoped chatbot.

Design constraints (see AGENTS.md):

* **No fabrication.** Every factual answer is assembled from excerpts of the
  workspace's *own* uploaded coursework. The retriever selects the passages; the
  composer only arranges them. If nothing relevant is found the assistant says
  so and points at the gap instead of inventing material.
* **Provenance is preserved.** Each answer carries citations naming the source
  document, the section heading and the page, so a student can verify the claim.
* **Subject isolation.** Retrieval is always filtered by ``workspace_id``; the
  assistant can never see another subject's material.
* **Deterministic.** No external service is required, so the assistant works
  offline exactly as the rest of the platform does. The same question against
  the same coursework yields the same answer.

The assistant also acts as a navigator: it can answer questions about the
student's own progress (gaps, visuals, examinations, mastery) directly from
persisted records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AcademicDocument,
    Examination,
    ExaminationAttempt,
    ExtractedContent,
    LearningOutcome,
    ResourceSufficiencyReport,
    SourceReference,
    SubjectWorkspace,
    Subtopic,
    Topic,
    VisualAsset,
    VisualStatus,
)
from . import analytics, textutil

MIN_PASSAGE_CHARS = 40
MAX_PASSAGES = 4
MAX_ANSWER_CHARS = 2600

# Intent keywords. Order matters: the first matching intent wins, so the more
# specific navigational intents are checked before the general "explain" intent.
_INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("gaps", ("gap", "missing", "sufficiency", "sufficient", "not covered",
              "incomplete", "coverage", "weak area", "what am i missing")),
    ("study", ("how do i study", "how should i study", "revision plan", "study plan",
               "how do i prepare", "how should i prepare", "prepare for", "tips", "advice")),
    ("visuals", ("visual", "diagram", "figure", "illustration", "chart", "svg")),
    ("exams", ("examination", "exam", "test", "paper", "blueprint", "memorandum",
               "mastery guide", "pdf", "deliverable")),
    ("progress", ("progress", "mark", "score", "grade", "perform", "performance",
                  "mastery", "result", "percentage", "how am i doing", "revision")),
    ("outcomes", ("learning outcome", "outcome", "objective", "what should i be able",
                  "syllabus")),
    ("topics", ("topic", "topics", "subtopic", "what does this subject cover",
                "what is covered", "list the topics")),
    ("explain", ("what is", "what are", "explain", "define", "definition", "describe",
                 "how does", "how do", "why", "summarise", "summarize", "tell me about",
                 "meaning of")),
]


@dataclass
class Passage:
    """A single retrieved coursework excerpt with its provenance."""

    content_id: str
    document_id: str
    document_name: str
    heading: str
    page: int
    text: str
    score: float

    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "content_id": self.content_id,
            "heading": self.heading,
            "page": self.page,
            "excerpt": _snippet(self.text, 240),
        }


@dataclass
class AssistantReply:
    content: str
    intent: str
    grounded: bool
    citations: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

def _snippet(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    # Prefer breaking on a sentence boundary so excerpts read cleanly.
    for stop in (". ", "! ", "? ", "; "):
        idx = cut.rfind(stop)
        if idx > limit * 0.5:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def _document_names(db: Session, workspace_id: str) -> dict[str, str]:
    docs = db.scalars(select(AcademicDocument).where(
        AcademicDocument.workspace_id == workspace_id))
    return {d.id: d.filename for d in docs}


def retrieve(db: Session, workspace_id: str, query: str,
             limit: int = MAX_PASSAGES) -> list[Passage]:
    """Return the workspace passages most relevant to ``query``.

    Scoring is lexical (term frequency weighted by inverse document frequency
    across the workspace's own chunks) with a bonus for the chunk heading. It is
    deliberately simple and explainable; it never reaches outside the workspace.
    """
    terms = textutil.content_tokens(query)
    contents = list(db.scalars(select(ExtractedContent).where(
        ExtractedContent.workspace_id == workspace_id)))
    if not contents:
        return []

    names = _document_names(db, workspace_id)
    doc_freq: dict[str, int] = {}
    for chunk in contents:
        for term in set(textutil.content_tokens(chunk.text)):
            doc_freq[term] = doc_freq.get(term, 0) + 1
    total = max(1, len(contents))

    scored: list[Passage] = []
    for chunk in contents:
        body = chunk.text or ""
        if len(body.strip()) < MIN_PASSAGE_CHARS:
            continue
        tokens = textutil.content_tokens(body)
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        heading_tokens = set(textutil.content_tokens(chunk.heading or ""))
        score = 0.0
        for term in terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            # Smoothed inverse document frequency keeps common terms from
            # dominating while still rewarding rare, specific ones.
            idf = 1.0 + (total / (1 + doc_freq.get(term, 0)))
            score += (1.0 + (frequency - 1) * 0.3) * idf
            if term in heading_tokens:
                score += idf * 1.5
        if score > 0:
            scored.append(Passage(
                content_id=chunk.id,
                document_id=chunk.document_id,
                document_name=names.get(chunk.document_id, "coursework"),
                heading=chunk.heading or "",
                page=chunk.page or 0,
                text=body,
                score=score,
            ))

    scored.sort(key=lambda p: (-p.score, p.document_name, p.page))
    return scored[:limit]


# --------------------------------------------------------------------------
# Intent detection
# --------------------------------------------------------------------------

def detect_intent(message: str) -> str:
    lowered = message.lower().strip()
    if not lowered:
        return "explain"
    for intent, keywords in _INTENTS:
        for keyword in keywords:
            if " " in keyword:
                if keyword in lowered:
                    return intent
            elif re.search(rf"\b{re.escape(keyword)}\w*\b", lowered):
                return intent
    return "explain"


# --------------------------------------------------------------------------
# Composers
# --------------------------------------------------------------------------

def _compose_explanation(message: str, passages: list[Passage]) -> AssistantReply:
    if not passages:
        return AssistantReply(
            content=("I could not find anything in this subject's uploaded coursework that "
                     "answers that. I only use the resources you uploaded for this subject, "
                     "so I will not guess. Upload the relevant lecture notes or slides, or "
                     "rephrase using terminology from your course material."),
            intent="explain", grounded=False,
            suggestions=["What topics does this subject cover?",
                         "What is missing from my coursework?",
                         "What learning outcomes should I meet?"],
        )

    lines: list[str] = ["Here is what your coursework says:\n"]
    for passage in passages:
        location = passage.document_name
        if passage.heading:
            location += f" › {passage.heading}"
        if passage.page:
            location += f" (p. {passage.page})"
        body = _snippet(passage.text, 420)
        lines.append(f"• {body}\n  — {location}")
    answer = "\n".join(lines)
    if len(answer) > MAX_ANSWER_CHARS:
        answer = answer[:MAX_ANSWER_CHARS].rstrip() + "\n…"
    return AssistantReply(
        content=answer, intent="explain", grounded=True,
        citations=[p.citation() for p in passages],
        suggestions=["Can you relate this to the exam?",
                     "What is missing from my coursework?",
                     "Which learning outcomes cover this?"],
    )


def _compose_topics(db: Session, workspace_id: str) -> AssistantReply:
    topics = list(db.scalars(select(Topic).where(
        Topic.workspace_id == workspace_id).order_by(Topic.confidence.desc())))
    if not topics:
        return AssistantReply(
            content=("No topics have been identified yet. Upload this subject's coursework "
                     "and run classification on the Topics & gaps tab."),
            intent="topics", grounded=False,
            suggestions=["What is missing from my coursework?"])
    lines = [f"This subject currently has {len(topics)} identified topic(s):\n"]
    for topic in topics:
        subtopics = list(db.scalars(select(Subtopic).where(Subtopic.topic_id == topic.id)))
        outcomes = list(db.scalars(select(LearningOutcome).where(
            LearningOutcome.topic_id == topic.id)))
        detail = f"• {topic.name} — coverage: {topic.coverage}"
        if subtopics:
            detail += f", {len(subtopics)} subtopic(s)"
        if outcomes:
            detail += f", {len(outcomes)} outcome(s)"
        lines.append(detail)
    return AssistantReply(
        content="\n".join(lines), intent="topics", grounded=True,
        suggestions=["What is missing from my coursework?",
                     "Which topics need diagrams?",
                     "What learning outcomes should I meet?"])


def _compose_outcomes(db: Session, workspace_id: str) -> AssistantReply:
    outcomes = list(db.scalars(select(LearningOutcome).where(
        LearningOutcome.workspace_id == workspace_id)))
    if not outcomes:
        return AssistantReply(
            content=("No learning outcomes have been derived yet. Classify this subject's "
                     "coursework first, then review them on the Topics & gaps tab."),
            intent="outcomes", grounded=False,
            suggestions=["What topics does this subject cover?"])
    topics = {t.id: t.name for t in db.scalars(select(Topic).where(
        Topic.workspace_id == workspace_id))}
    lines = [f"{len(outcomes)} learning outcome(s) have been derived:\n"]
    for outcome in outcomes[:25]:
        topic = topics.get(outcome.topic_id, "")
        lines.append(f"• [{outcome.bloom}] {outcome.statement}"
                     + (f"  ({topic})" if topic else ""))
    return AssistantReply(
        content="\n".join(lines), intent="outcomes", grounded=True,
        suggestions=["What is missing from my coursework?",
                     "How should I prepare for the examination?"])


def _compose_gaps(db: Session, workspace: SubjectWorkspace) -> AssistantReply:
    report = db.scalars(select(ResourceSufficiencyReport).where(
        ResourceSufficiencyReport.workspace_id == workspace.id
    ).order_by(ResourceSufficiencyReport.created_at.desc())).first()
    if report is None:
        return AssistantReply(
            content=("No sufficiency assessment exists yet. Upload this subject's coursework "
                     "and run classification to produce one."),
            intent="gaps", grounded=False,
            suggestions=["What topics does this subject cover?"])
    lines = [f"Resource sufficiency verdict: {report.verdict}.",
             f"Assessed from {report.document_count} document(s), "
             f"{report.total_chars:,} extracted character(s).\n"]
    for label, entries in (("Adequately covered", report.adequate),
                           ("Partially covered", report.partial),
                           ("Missing", report.missing),
                           ("Missing learning outcomes", report.missing_outcomes),
                           ("Conflicting material", report.conflicts),
                           ("Insufficient for some question types", report.insufficient_types),
                           ("Needs clarification", report.clarifications)):
        if entries:
            lines.append(f"{label}: " + "; ".join(str(e) for e in entries[:8]))
    if len(lines) == 2:
        lines.append("No gaps were detected in the uploaded material.")
    lines.append("\nI will not invent material to fill gaps — upload the missing resources "
                 "to improve examination quality.")
    return AssistantReply(
        content="\n".join(lines), intent="gaps", grounded=True,
        suggestions=["What topics does this subject cover?",
                     "Which topics need diagrams?",
                     "How should I prepare for the examination?"])


def _compose_visuals(db: Session, workspace_id: str) -> AssistantReply:
    assets = list(db.scalars(select(VisualAsset).where(
        VisualAsset.workspace_id == workspace_id)))
    topics = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace_id)))
    needing = [t for t in topics if t.needs_visual and t.needs_visual != "unnecessary"]
    lines: list[str] = []
    if assets:
        approved = sum(1 for a in assets if a.status == VisualStatus.APPROVED.value)
        lines.append(f"{len(assets)} visual asset(s); {approved} approved. Details:")
        for asset in assets[:15]:
            lines.append(f"• {asset.title} — {asset.diagram_type} "
                         f"[{asset.status}] (requirement: {asset.requirement})")
    else:
        lines.append("No visual assets have been proposed yet. Use the Visuals tab to "
                     "analyse requirements and construct diagrams.")
    if needing:
        lines.append("\nTopics assessed as needing a visual:")
        for topic in needing[:12]:
            reason = f" — {topic.visual_rationale}" if topic.visual_rationale else ""
            lines.append(f"• {topic.name} ({topic.needs_visual}){reason}")
    return AssistantReply(
        content="\n".join(lines), intent="visuals", grounded=True,
        suggestions=["What topics does this subject cover?",
                     "How should I prepare for the examination?"])


def _compose_exams(db: Session, workspace_id: str) -> AssistantReply:
    examinations = list(db.scalars(select(Examination).where(
        Examination.workspace_id == workspace_id).order_by(Examination.created_at.desc())))
    if not examinations:
        return AssistantReply(
            content=("No examinations have been generated for this subject yet. Configure a "
                     "blueprint on the Examinations tab to generate one."),
            intent="exams", grounded=False,
            suggestions=["What is missing from my coursework?",
                         "Which topics need diagrams?"])
    lines = [f"{len(examinations)} examination(s) for this subject:\n"]
    for exam in examinations[:12]:
        lines.append(f"• {exam.title} (v{exam.version}, {exam.mode}) — "
                     f"{exam.total_marks} marks, {exam.duration_minutes} min, "
                     f"status: {exam.status}, moderation: {exam.moderation_status}")
    lines.append("\nThe memorandum and subject mastery guide are generated per examination "
                 "and stay withheld in formal mode until feedback is released.")
    return AssistantReply(
        content="\n".join(lines), intent="exams", grounded=True,
        suggestions=["How am I performing in this subject?",
                     "How should I prepare for the examination?"])


def _compose_progress(db: Session, workspace_id: str) -> AssistantReply:
    report = analytics.analyse_workspace(db, workspace_id)
    attempts = report.get("attempts", 0)
    if not attempts:
        return AssistantReply(
            content=("You have no submitted attempts in this subject yet, so there is no "
                     "performance evidence to analyse. Sit a practice examination and I can "
                     "identify your strong and weak topics from the actual marking records."),
            intent="progress", grounded=False,
            suggestions=["How should I prepare for the examination?",
                         "What is missing from my coursework?"])
    lines = [f"Based on {attempts} submitted attempt(s):"]
    average = report.get("average_percentage")
    if average is not None:
        lines.append(f"• Overall average: {average:.1f}%")
    mastery = report.get("mastery") or {}
    if mastery:
        lines.append("• Mastery by topic: " + ", ".join(
            f"{name}={level}" for name, level in list(mastery.items())[:10]))
    weak = [row for row in report.get("by_topic", []) if row.get("percentage") is not None
            and row["percentage"] < 60]
    if weak:
        lines.append("• Weakest topics: " + "; ".join(
            f"{row.get('name')} ({row['percentage']:.0f}%)" for row in weak[:5]))
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("\nRecommended revision focus:")
        for item in recommendations[:5]:
            lines.append(f"• {item}")
    return AssistantReply(
        content="\n".join(lines), intent="progress", grounded=True,
        suggestions=["What is missing from my coursework?",
                     "Which topics need diagrams?"])


def _compose_study(db: Session, workspace: SubjectWorkspace) -> AssistantReply:
    report = db.scalars(select(ResourceSufficiencyReport).where(
        ResourceSufficiencyReport.workspace_id == workspace.id
    ).order_by(ResourceSufficiencyReport.created_at.desc())).first()
    topics = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace.id)))
    gaps = report.partial + report.missing if report else []
    lines = ["A grounded preparation approach for this subject:\n",
             "1. Work topic by topic, not cover to cover — your topics are:"]
    for topic in topics[:10]:
        lines.append(f"   • {topic.name} (coverage: {topic.coverage})")
    if gaps:
        lines.append("\n2. Close the gaps first — these are partial or missing:")
        for gap in gaps[:8]:
            lines.append(f"   • {gap}")
    lines.append("\n3. For each topic, explain it aloud from memory, then check against the "
                 "source excerpt. Use active recall rather than re-reading.")
    lines.append("4. Reconstruct any required diagrams from memory before checking them.")
    lines.append("5. Sit a practice examination, then revise only the topics the marking "
                 "record shows as weak.")
    lines.append("\nI recommend active recall and worked examples for applied topics; only "
                 "resort to pure memorisation where the outcome is genuinely recall.")
    return AssistantReply(
        content="\n".join(lines), intent="study", grounded=bool(topics),
        suggestions=["What is missing from my coursework?",
                     "How am I performing in this subject?"])


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def answer(db: Session, workspace: SubjectWorkspace, message: str) -> AssistantReply:
    """Produce a grounded reply to one student message."""
    intent = detect_intent(message)

    if intent == "topics":
        return _compose_topics(db, workspace.id)
    if intent == "outcomes":
        return _compose_outcomes(db, workspace.id)
    if intent == "gaps":
        return _compose_gaps(db, workspace)
    if intent == "visuals":
        return _compose_visuals(db, workspace.id)
    if intent == "exams":
        return _compose_exams(db, workspace.id)
    if intent == "progress":
        return _compose_progress(db, workspace.id)
    if intent == "study":
        return _compose_study(db, workspace)

    # Default: answer from the workspace's own coursework. If nothing relevant
    # is found the reply explains that honestly rather than fabricating content.
    passages = retrieve(db, workspace.id, message)
    return _compose_explanation(message, passages)


def title_for(message: str) -> str:
    """Derive a short conversation title from its first message."""
    clean = re.sub(r"\s+", " ", message).strip()
    if not clean:
        return "New conversation"
    if len(clean) <= 60:
        return clean
    return clean[:57].rstrip() + "…"


def sources_for(db: Session, workspace_id: str, entity_type: str,
                entity_id: str) -> list[dict]:
    """Resolve stored provenance references for an entity (used for traceability)."""
    refs = db.scalars(select(SourceReference).where(
        SourceReference.workspace_id == workspace_id,
        SourceReference.entity_type == entity_type,
        SourceReference.entity_id == entity_id))
    return [{"document_id": r.document_id, "content_id": r.content_id,
             "locator": r.locator, "quote": r.quote} for r in refs]
