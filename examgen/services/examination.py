"""Examination lifecycle: blueprint -> generation -> moderation -> publication ->
attempt -> submission -> marking -> PDF deliverables.

Published examinations store an immutable snapshot of their questions, visuals
and document versions. Later edits to the workspace never alter a published
examination, which is what guarantees version consistency across the website,
the memorandum and the mastery guide.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AnswerKey,
    AttemptStatus,
    Difficulty,
    Examination,
    ExaminationAttempt,
    ExaminationBlueprint,
    ExamMode,
    ExamStatus,
    ExtractedContent,
    LearningOutcome,
    MarkingRecord,
    MarkingRubric,
    ModerationStatus,
    PDFDeliverable,
    PDFKind,
    Provenance,
    Question,
    QuestionType,
    SourceReference,
    StudentResponse,
    SubjectWorkspace,
    Submission,
    Topic,
    VisualAsset,
    VisualRequirement,
)
from . import analytics, generation, marking, moderation, pdf, textutil, workspace as ws


# --------------------------------------------------------------------------
# Blueprint
# --------------------------------------------------------------------------

def validate_blueprint(db: Session, workspace: SubjectWorkspace,
                       blueprint: ExaminationBlueprint) -> dict:
    """Validate topic coverage, marks, duration and question distribution."""
    topics = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace.id)))
    selected = [t for t in topics if not blueprint.topic_ids or t.id in set(blueprint.topic_ids)]
    contents = list(db.scalars(select(ExtractedContent).where(
        ExtractedContent.workspace_id == workspace.id)))
    issues: list[str] = []
    warnings: list[str] = []

    if not selected:
        issues.append("No topics are available. Upload coursework and classify the subject first.")
    if not contents:
        issues.append("No extracted content is available for the selected subject.")

    type_total = sum(blueprint.type_distribution.values()) if blueprint.type_distribution else 0
    if blueprint.type_distribution and type_total <= 0:
        issues.append("Question-type distribution sums to zero.")

    difficulty_total = (sum(blueprint.difficulty_distribution.values())
                        if blueprint.difficulty_distribution else 0)
    if blueprint.difficulty_distribution and difficulty_total <= 0:
        issues.append("Difficulty distribution sums to zero.")

    marks_per_question = blueprint.total_marks / blueprint.question_count
    if marks_per_question < 1:
        issues.append("Total marks are fewer than the number of questions.")
    if marks_per_question > 25:
        warnings.append(
            f"Average of {marks_per_question:.1f} marks per question is unusually high.")

    minutes_per_mark = blueprint.duration_minutes / max(blueprint.total_marks, 1)
    if minutes_per_mark < 0.6:
        issues.append(
            f"Only {minutes_per_mark:.2f} minutes per mark — the paper cannot be completed.")
    elif minutes_per_mark > 4:
        warnings.append(f"{minutes_per_mark:.2f} minutes per mark is generous.")

    # Coverage: is there enough material per topic for the requested count?
    per_topic = blueprint.question_count / max(len(selected), 1)
    thin = [t.name for t in selected if t.coverage != "adequate"]
    if thin:
        warnings.append(
            "These topics have partial coverage and may produce weaker questions: "
            + ", ".join(thin[:6]))

    insufficient: list[str] = []
    has_numeric = any(textutil.has_numeric_content(c.text) for c in contents)
    if not has_numeric:
        insufficient.append("numerical")
    if not any(c.kind == "formula" for c in contents):
        insufficient.append("formula")
    if len(selected) < 2:
        insufficient.append("matching")
    if sum(len(c.text) for c in contents) < 2500:
        insufficient.append("extended_response")

    approved_visuals = list(db.scalars(select(VisualAsset).where(
        VisualAsset.workspace_id == workspace.id,
        VisualAsset.status == "approved")))
    required_visuals = [t for t in selected
                        if t.needs_visual == VisualRequirement.ESSENTIAL.value]
    if required_visuals and not approved_visuals:
        warnings.append(
            f"{len(required_visuals)} topic(s) require visual assessment but no visual "
            "assets have been approved yet.")

    result = {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "insufficient_question_types": insufficient,
        "topic_count": len(selected),
        "content_chars": sum(len(c.text) for c in contents),
        "average_marks_per_question": round(marks_per_question, 2),
        "minutes_per_mark": round(minutes_per_mark, 2),
        "approved_visuals": len(approved_visuals),
    }
    blueprint.validation = result
    blueprint.is_valid = not issues
    db.flush()
    return result


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def _persist_question(db: Session, draft: generation.QuestionDraft,
                      workspace_id: str, fingerprint_index: dict[str, Question]) -> Question:
    existing = fingerprint_index.get(draft.fingerprint())
    if existing is not None:
        existing.version += 1
        db.flush()
        return existing
    question = Question(
        workspace_id=workspace_id,
        topic_id=draft.topic_id,
        subtopic_id=draft.subtopic_id,
        learning_outcome_id=draft.outcome_id,
        visual_asset_id=draft.visual_asset_id,
        visual_version=draft.visual_version,
        fingerprint=draft.fingerprint(),
        qtype=draft.qtype,
        difficulty=draft.difficulty,
        bloom=draft.bloom,
        prompt=draft.prompt,
        instructions=draft.instructions,
        marks=draft.marks,
        options=draft.options,
        payload=draft.payload,
        expected_answer=draft.expected_answer,
        acceptable_alternatives=draft.acceptable_alternatives,
        explanation=draft.explanation,
        common_errors=draft.common_errors,
        provenance=draft.provenance,
        source_document_ids=draft.source_document_ids,
        validated=not draft.validation_notes,
        validation_notes=draft.validation_notes,
    )
    db.add(question)
    db.flush()
    key = {
        QuestionType.FILL_BLANK.value: {"text": draft.expected_answer},
        QuestionType.SINGLE_CHOICE.value: {
            "text": draft.expected_answer,
            "index": draft.options.index(draft.expected_answer)
            if draft.expected_answer in draft.options else None,
        },
        QuestionType.MULTIPLE_CHOICE.value: {"correct": draft.payload.get("correct", [])},
        QuestionType.MATCHING.value: {
            "pairs": {i["prompt"]: i["answer"] for i in draft.payload.get("items", [])}},
        QuestionType.NUMERICAL.value: {"value": draft.expected_answer, "tolerance": 0.0},
        QuestionType.ORDERING.value: {"order": draft.payload.get("correct_order", [])},
    }.get(draft.qtype, {})
    db.add(AnswerKey(
        question_id=question.id, workspace_id=workspace_id,
        correct=key, acceptable=draft.acceptable_alternatives,
        deterministic=marking.is_objective(draft.qtype)))
    for rubric in draft.rubrics:
        db.add(MarkingRubric(
            question_id=question.id, workspace_id=workspace_id,
            criterion=rubric.get("criterion", ""), marks=int(rubric.get("marks", 1)),
            guidance=rubric.get("guidance", ""),
            partial_credit=bool(rubric.get("partial_credit", True))))
    for content_id in draft.source_content_ids:
        db.add(SourceReference(
            workspace_id=workspace_id, entity_type="question", entity_id=question.id,
            content_id=content_id, locator="generated question",
            quote=draft.prompt[:300], provenance=draft.provenance))
    db.flush()
    fingerprint_index[question.fingerprint] = question
    return question


def _question_snapshot(db: Session, question: Question, topic_names: dict[str, str],
                       section: str) -> dict:
    rubrics = [{"criterion": r.criterion, "marks": r.marks, "guidance": r.guidance,
                "partial_credit": r.partial_credit}
               for r in db.scalars(select(MarkingRubric).where(
                   MarkingRubric.question_id == question.id))]
    return {
        "question_id": question.id,
        "qtype": question.qtype,
        "prompt": question.prompt,
        "instructions": question.instructions,
        "marks": question.marks,
        "difficulty": question.difficulty,
        "bloom": question.bloom,
        "options": question.options or [],
        "payload": question.payload or {},
        "expected_answer": question.expected_answer,
        "acceptable_alternatives": question.acceptable_alternatives or [],
        "explanation": question.explanation,
        "common_errors": question.common_errors or [],
        "rubrics": rubrics,
        "topic_id": question.topic_id,
        "topic_name": topic_names.get(question.topic_id or "", "Unclassified"),
        "subtopic_id": question.subtopic_id,
        "learning_outcome_id": question.learning_outcome_id,
        "visual_asset_id": question.visual_asset_id,
        "visual_version": question.visual_version,
        "provenance": question.provenance,
        "source_document_ids": question.source_document_ids or [],
        "fingerprint": question.fingerprint,
        "validation_notes": question.validation_notes,
        "section": section,
    }


def generate_examination(db: Session, workspace: SubjectWorkspace,
                         blueprint: ExaminationBlueprint, mode: str,
                         user_id: str | None = None) -> Examination:
    """Generate, moderate and (if approved) publish an examination."""
    validation = validate_blueprint(db, workspace, blueprint)
    if not validation["valid"]:
        raise ValueError("Blueprint validation failed: " + "; ".join(validation["issues"]))

    bundles = ws.topic_bundles(db, workspace.id, blueprint.topic_ids)
    if not bundles:
        raise ValueError("No material available in this subject workspace.")

    assets = list(db.scalars(select(VisualAsset).where(
        VisualAsset.workspace_id == workspace.id)))
    if blueprint.required_visual_keys:
        assets = [a for a in assets if a.key in set(blueprint.required_visual_keys)] or assets

    existing_fingerprints = {q.fingerprint for q in db.scalars(select(Question).where(
        Question.workspace_id == workspace.id, Question.in_bank.is_(True)))}

    version = 1 + len([e for e in db.scalars(select(Examination).where(
        Examination.workspace_id == workspace.id))])

    drafts = generation.generate_questions(
        workspace_id=workspace.id,
        blueprint_id=blueprint.id,
        version=version,
        question_count=blueprint.question_count,
        total_marks=blueprint.total_marks,
        topic_bundles=bundles,
        assets=assets,
        type_distribution=blueprint.type_distribution or None,
        difficulty_distribution=blueprint.difficulty_distribution or None,
        bloom_distribution=blueprint.bloom_distribution or None,
        required_visual_keys=blueprint.required_visual_keys or None,
        existing_fingerprints=set(),
    )
    if not drafts:
        raise ValueError("Question generation produced no questions from the available material.")

    fingerprint_index = {q.fingerprint: q for q in db.scalars(select(Question).where(
        Question.workspace_id == workspace.id))}
    topic_names = {t.id: t.name for t in db.scalars(select(Topic).where(
        Topic.workspace_id == workspace.id))}

    snapshot: list[dict] = []
    for draft in drafts:
        question = _persist_question(db, draft, workspace.id, fingerprint_index)
        snapshot.append(_question_snapshot(
            db, question, topic_names,
            draft.payload.get("section", "Section A — Objective")))

    visual_ids = {q["visual_asset_id"] for q in snapshot if q.get("visual_asset_id")}
    visual_snapshot: dict[str, dict] = {}
    for asset in db.scalars(select(VisualAsset).where(VisualAsset.id.in_(visual_ids))) if visual_ids else []:
        visual_snapshot[asset.id] = {
            "id": asset.id, "key": asset.key, "title": asset.title,
            "diagram_type": asset.diagram_type, "version": asset.version,
            "status": asset.status, "labels": asset.labels or [],
            "svg": asset.svg, "spec": asset.spec or {},
            "intended_use": asset.intended_use,
        }

    document_versions = {}
    for document in db.scalars(select(ws.AcademicDocument).where(  # type: ignore[attr-defined]
            ws.AcademicDocument.workspace_id == workspace.id,
            ws.AcademicDocument.is_latest.is_(True))):
        document_versions[document.id] = {"filename": document.filename,
                                          "version": document.version,
                                          "sha256": document.sha256[:16]}

    sections: dict[str, dict] = {}
    for question in snapshot:
        section = question["section"]
        entry = sections.setdefault(section, {"name": section, "marks": 0, "questions": []})
        entry["marks"] += question["marks"]
        entry["questions"].append(question["question_id"])

    total_marks = sum(q["marks"] for q in snapshot)
    examination = Examination(
        workspace_id=workspace.id,
        blueprint_id=blueprint.id,
        title=blueprint.title,
        subject_name=workspace.name,
        module_name=workspace.module,
        version=version,
        mode=mode if mode in {ExamMode.PRACTICE.value, ExamMode.FORMAL.value}
        else ExamMode.PRACTICE.value,
        status=ExamStatus.DRAFT.value,
        duration_minutes=blueprint.duration_minutes,
        total_marks=total_marks,
        instructions=blueprint.instructions or _default_instructions(blueprint, total_marks),
        sections=list(sections.values()),
        question_snapshot=snapshot,
        visual_snapshot=visual_snapshot,
        document_versions=document_versions,
    )
    db.add(examination)
    db.flush()

    result = moderation.moderate(examination)
    examination.moderation_status = result.status
    examination.moderation_findings = [f.as_dict() for f in result.findings]
    if result.can_publish:
        examination.status = ExamStatus.PUBLISHED.value
        examination.published_at = datetime.now(timezone.utc)
    examination.content_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    db.flush()
    ws.audit(db, workspace.id, user_id, "examination.generated", "examination", examination.id,
             {"version": version, "questions": len(snapshot),
              "moderation": result.status, "published": result.can_publish})
    return examination


def _default_instructions(blueprint: ExaminationBlueprint, total_marks: int) -> str:
    return (
        f"Answer ALL questions. Total marks: {total_marks}. "
        f"Time allowed: {blueprint.duration_minutes} minutes. "
        "Read each question carefully before answering. "
        "For fill-in questions, type your answer in the text box provided. "
        "For selection questions, choose your answer from the dropdown list. "
        "Where multiple answers are required, select every correct option. "
        "Show all working for calculation questions and state units in your final answer. "
        "Answers are saved automatically as you work."
    )


def remoderate(db: Session, examination: Examination) -> moderation.ModerationResult:
    result = moderation.moderate(examination)
    examination.moderation_status = result.status
    examination.moderation_findings = [f.as_dict() for f in result.findings]
    if result.can_publish and examination.status == ExamStatus.DRAFT.value:
        examination.status = ExamStatus.PUBLISHED.value
        examination.published_at = datetime.now(timezone.utc)
    db.flush()
    return result


# --------------------------------------------------------------------------
# Public view
# --------------------------------------------------------------------------

def public_questions(examination: Examination, include_answers: bool = False) -> list[dict]:
    questions: list[dict] = []
    for ordinal, question in enumerate(examination.question_snapshot or [], start=1):
        visual = (examination.visual_snapshot or {}).get(question.get("visual_asset_id") or "")
        entry = {
            "question_id": question["question_id"],
            "ordinal": ordinal,
            "section": question.get("section", ""),
            "qtype": question["qtype"],
            "prompt": question["prompt"],
            "instructions": question.get("instructions", ""),
            "marks": question["marks"],
            "difficulty": question.get("difficulty", ""),
            "bloom": question.get("bloom", ""),
            "options": question.get("options", []),
            "payload": question.get("payload", {}),
            "visual": ({"id": visual["id"], "title": visual["title"],
                        "diagram_type": visual["diagram_type"], "version": visual["version"],
                        "labels": visual["labels"], "svg": visual["svg"]}
                       if visual else None),
        }
        if include_answers:
            entry["expected_answer"] = question.get("expected_answer", "")
            entry["explanation"] = question.get("explanation", "")
            entry["rubrics"] = question.get("rubrics", [])
        questions.append(entry)
    return questions


# --------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------

def start_attempt(db: Session, examination: Examination, student_id: str,
                  student_name: str, student_number: str, mode: str) -> ExaminationAttempt:
    if examination.status != ExamStatus.PUBLISHED.value:
        raise ValueError("This examination has not been published.")
    previous = list(db.scalars(select(ExaminationAttempt).where(
        ExaminationAttempt.examination_id == examination.id,
        ExaminationAttempt.student_id == student_id)))
    attempt = ExaminationAttempt(
        examination_id=examination.id,
        workspace_id=examination.workspace_id,
        student_id=student_id,
        student_name=student_name,
        student_number=student_number,
        mode=mode if mode in {ExamMode.PRACTICE.value, ExamMode.FORMAL.value} else examination.mode,
        status=AttemptStatus.IN_PROGRESS.value,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=examination.duration_minutes),
        attempt_no=len(previous) + 1,
        max_score=float(examination.total_marks),
    )
    db.add(attempt)
    db.flush()
    ws.audit(db, examination.workspace_id, student_id, "attempt.started", "attempt",
             attempt.id, {"examination_id": examination.id, "mode": attempt.mode})
    return attempt


def save_responses(db: Session, attempt: ExaminationAttempt,
                   responses: list[dict]) -> ExaminationAttempt:
    """Autosave — upserts responses and refreshes the deadline on formal attempts."""
    if attempt.status not in {AttemptStatus.IN_PROGRESS.value, AttemptStatus.EXPIRED.value}:
        raise ValueError("This attempt has already been submitted.")
    valid_ids = {q["question_id"] for q in (db.get(Examination, attempt.examination_id)
                                            .question_snapshot or [])}
    now = datetime.now(timezone.utc)
    for item in responses:
        question_id = item.get("question_id")
        if question_id not in valid_ids:
            continue
        answer = item.get("answer") or {}
        flagged = bool(item.get("flagged"))
        answered = _is_answered(answer)
        existing = db.scalars(select(StudentResponse).where(
            StudentResponse.attempt_id == attempt.id,
            StudentResponse.question_id == question_id)).first()
        if existing is None:
            db.add(StudentResponse(
                attempt_id=attempt.id, question_id=question_id, answer=answer,
                flagged=flagged, answered=answered, autosaved_at=now))
        else:
            existing.answer = answer
            existing.flagged = flagged
            existing.answered = answered
            existing.autosaved_at = now
    db.flush()
    return attempt


def _is_answered(answer: dict) -> bool:
    for key in ("value", "text", "selected", "order", "matches", "index"):
        value = answer.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, dict)) and len(value) > 0:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
    return False


def submit_attempt(db: Session, attempt: ExaminationAttempt,
                   student_id: str) -> ExaminationAttempt:
    if attempt.student_id != student_id:
        raise ValueError("This attempt belongs to another student.")
    if attempt.status == AttemptStatus.SUBMITTED.value:
        return attempt
    examination = db.get(Examination, attempt.examination_id)
    now = datetime.now(timezone.utc)
    responses = list(db.scalars(select(StudentResponse).where(
        StudentResponse.attempt_id == attempt.id)))
    attempt.status = AttemptStatus.SUBMITTED.value
    attempt.submitted_at = now
    db.add(Submission(
        attempt_id=attempt.id, workspace_id=attempt.workspace_id, kind="manual",
        confirmed=True, response_count=sum(1 for r in responses if r.answered),
        snapshot={"responses": [
            {"question_id": r.question_id, "answer": r.answer, "flagged": r.flagged}
            for r in responses]},
    ))
    db.flush()
    mark_attempt(db, attempt, examination)
    ws.audit(db, attempt.workspace_id, student_id, "attempt.submitted", "attempt",
             attempt.id, {"score": attempt.score, "percentage": attempt.percentage})
    return attempt


def mark_attempt(db: Session, attempt: ExaminationAttempt,
                 examination: Examination) -> ExaminationAttempt:
    """Mark all responses: deterministic for objective, rubric-based for extended."""
    snapshot = {q["question_id"]: q for q in (examination.question_snapshot or [])}
    responses = {r.question_id: r for r in db.scalars(select(StudentResponse).where(
        StudentResponse.attempt_id == attempt.id))}
    for record in db.scalars(select(MarkingRecord).where(
            MarkingRecord.attempt_id == attempt.id)):
        db.delete(record)
    db.flush()

    total = 0.0
    max_total = 0.0
    for question_id, question in snapshot.items():
        response = responses.get(question_id)
        answer = (response.answer if response else {}) or {}
        max_marks = float(question["marks"])
        max_total += max_marks
        # Rehydrate a lightweight Question-like view for the marker.
        proxy = _QuestionProxy(question, db)
        result = marking.mark(proxy, answer)
        total += result.awarded
        db.add(MarkingRecord(
            attempt_id=attempt.id, question_id=question_id,
            workspace_id=attempt.workspace_id,
            awarded=result.awarded, max_marks=result.max_marks, method=result.method,
            rationale=result.rationale, needs_human_review=result.needs_human_review,
            breakdown=result.breakdown))
    attempt.score = round(total, 2)
    attempt.max_score = round(max_total, 2)
    attempt.percentage = round(total / max_total * 100, 2) if max_total else 0.0
    attempt.status = AttemptStatus.MARKED.value
    attempt.feedback_released = attempt.mode == ExamMode.PRACTICE.value
    db.flush()
    return attempt


class _QuestionProxy:
    """Adapts an immutable question snapshot to the marking interface."""

    def __init__(self, snapshot: dict, db: Session):
        self.qtype = snapshot["qtype"]
        self.marks = snapshot["marks"]
        self.options = snapshot.get("options", [])
        self.payload = snapshot.get("payload", {})
        self.expected_answer = snapshot.get("expected_answer", "")
        self.acceptable_alternatives = snapshot.get("acceptable_alternatives", [])
        self.answer_key = _KeyProxy(snapshot)
        self.rubrics = [_RubricProxy(r) for r in snapshot.get("rubrics", [])]


class _KeyProxy:
    def __init__(self, snapshot: dict):
        self.correct = {
            QuestionType.FILL_BLANK.value: {"text": snapshot.get("expected_answer", "")},
            QuestionType.SINGLE_CHOICE.value: {
                "text": snapshot.get("expected_answer", ""),
                "index": (snapshot.get("options") or []).index(snapshot["expected_answer"])
                if snapshot.get("expected_answer") in (snapshot.get("options") or []) else None,
            },
            QuestionType.MULTIPLE_CHOICE.value: {
                "correct": (snapshot.get("payload") or {}).get("correct", [])},
            QuestionType.MATCHING.value: {
                "pairs": {i["prompt"]: i["answer"]
                          for i in (snapshot.get("payload") or {}).get("items", [])}},
            QuestionType.NUMERICAL.value: {"value": snapshot.get("expected_answer", ""),
                                           "tolerance": 0.0},
            QuestionType.ORDERING.value: {
                "order": (snapshot.get("payload") or {}).get("correct_order", [])},
        }.get(snapshot["qtype"], {})


class _RubricProxy:
    def __init__(self, rubric: dict):
        self.criterion = rubric.get("criterion", "")
        self.marks = rubric.get("marks", 1)
        self.guidance = rubric.get("guidance", "")
        self.partial_credit = rubric.get("partial_credit", True)


def release_feedback(db: Session, examination: Examination,
                     user_id: str | None) -> int:
    """Formal mode: release answer keys and memoranda only when authorised."""
    count = 0
    for attempt in db.scalars(select(ExaminationAttempt).where(
            ExaminationAttempt.examination_id == examination.id)):
        if not attempt.feedback_released:
            attempt.feedback_released = True
            count += 1
    for deliverable in db.scalars(select(PDFDeliverable).where(
            PDFDeliverable.examination_id == examination.id,
            PDFDeliverable.kind == PDFKind.MEMORANDUM.value)):
        deliverable.released = True
    db.flush()
    ws.audit(db, examination.workspace_id, user_id, "feedback.released", "examination",
             examination.id, {"attempts": count})
    return count


# --------------------------------------------------------------------------
# PDF deliverables
# --------------------------------------------------------------------------

def _examination_meta(examination: Examination) -> dict:
    return {
        "id": examination.id,
        "title": examination.title,
        "subject_name": examination.subject_name,
        "module_name": examination.module_name,
        "version": examination.version,
        "mode": examination.mode,
        "duration_minutes": examination.duration_minutes,
        "total_marks": examination.total_marks,
        "moderation_status": examination.moderation_status,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "assessment_objectives": (examination.sections and [
            s.get("name", "") for s in examination.sections]) or [],
    }


def generate_deliverables(db: Session, examination: Examination,
                          user_id: str | None = None) -> dict:
    """Produce both PDFs for the current examination version."""
    settings = get_settings()
    questions = examination.question_snapshot or []
    visuals = examination.visual_snapshot or {}
    meta = _examination_meta(examination)
    base = f"exam_{examination.id[:12]}_v{examination.version}"

    memo_path = settings.data_dir / "pdf" / f"{base}_memorandum.pdf"
    pdf.build_memorandum(memo_path, meta, questions, visuals)

    topics: list[dict] = []
    definitions: dict[str, list[str]] = {}
    formulas: dict[str, list[str]] = {}
    for topic in db.scalars(select(Topic).where(
            Topic.workspace_id == examination.workspace_id)):
        subtopics = list(db.scalars(select(ws.Subtopic).where(  # type: ignore[attr-defined]
            ws.Subtopic.topic_id == topic.id)))
        outcomes = list(db.scalars(select(LearningOutcome).where(
            LearningOutcome.topic_id == topic.id)))
        contents = list(db.scalars(select(ExtractedContent).where(
            ExtractedContent.workspace_id == examination.workspace_id)))
        topic_contents = [c for c in contents
                          if any(str(k).lower() in c.text.lower()
                                 for k in (topic.keywords or [])[:5])][:40]
        definitions[topic.id] = _definitions_from(topic_contents)
        formulas[topic.id] = _formulas_from(topic_contents)
        topics.append({
            "id": topic.id,
            "name": topic.name,
            "summary": topic.summary,
            "coverage": topic.coverage,
            "key_points": [str(k) for k in (topic.keywords or [])][:8],
            "outcomes": [{"statement": o.statement, "bloom": o.bloom} for o in outcomes],
            "subtopics": [
                {"name": s.name, "summary": s.summary,
                 "outcomes": [{"statement": o.statement}
                              for o in outcomes if o.subtopic_id == s.id]}
                for s in subtopics],
            "visual_ids": [v.id for v in db.scalars(select(VisualAsset).where(
                VisualAsset.topic_id == topic.id, VisualAsset.status == "approved"))],
        })

    performance = analytics.analyse_workspace(db, examination.workspace_id)
    mastery_path = settings.data_dir / "pdf" / f"{base}_mastery.pdf"
    pdf.build_mastery_guide(mastery_path, meta, topics, questions, visuals,
                            performance, definitions, formulas)

    deliverables: dict[str, dict] = {}
    for kind, path in ((PDFKind.MEMORANDUM.value, memo_path),
                       (PDFKind.MASTERY_GUIDE.value, mastery_path)):
        existing = db.scalars(select(PDFDeliverable).where(
            PDFDeliverable.examination_id == examination.id,
            PDFDeliverable.kind == kind,
            PDFDeliverable.exam_version == examination.version)).first()
        digest = pdf.file_hash(path)
        if existing is None:
            existing = PDFDeliverable(
                examination_id=examination.id, workspace_id=examination.workspace_id,
                kind=kind, path=str(path), exam_version=examination.version,
                content_hash=digest,
                released=(kind == PDFKind.MEMORANDUM.value
                          and examination.mode == ExamMode.PRACTICE.value))
            db.add(existing)
        else:
            existing.path = str(path)
            existing.content_hash = digest
        db.flush()
        deliverables[kind] = {
            "id": existing.id, "path": str(path), "version": examination.version,
            "released": existing.released, "content_hash": digest,
        }
    ws.audit(db, examination.workspace_id, user_id, "deliverables.generated",
             "examination", examination.id, {"version": examination.version})
    return deliverables


def _definitions_from(contents: list[ExtractedContent]) -> list[str]:
    import re

    pattern = re.compile(
        r"\b(?P<term>[A-Z][A-Za-z0-9 \-]{2,50}?)\s+"
        r"(?:is|are|refers to|means|is defined as|denotes)\s+(?P<body>.+?)(?:\.|$)")
    found: list[str] = []
    seen: set[str] = set()
    for content in contents:
        for match in pattern.finditer(content.text):
            term = match.group("term").strip()
            if term.lower() in seen or len(term) < 3:
                continue
            seen.add(term.lower())
            found.append(f"{term}: {match.group('body').strip()[:240]}")
            if len(found) >= 14:
                return found
    return found


def _formulas_from(contents: list[ExtractedContent]) -> list[str]:
    import re

    found: list[str] = []
    seen: set[str] = set()
    for content in contents:
        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9_]*\s*=\s*[^=\n]{1,70}", content.text):
            formula = match.group(0).strip()
            if formula in seen or len(formula) < 5:
                continue
            seen.add(formula)
            found.append(formula)
            if len(found) >= 10:
                return found
    return found
