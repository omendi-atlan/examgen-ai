"""Examination endpoints: blueprints, generation, moderation, attempts, marking."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (
    AttemptStatus,
    Examination,
    ExaminationAttempt,
    ExaminationBlueprint,
    ExamMode,
    ExamStatus,
    MarkingRecord,
    PDFDeliverable,
    PDFKind,
    StudentResponse,
    SubjectWorkspace,
    User,
)
from ...schemas import (
    AttemptOut,
    AttemptStartRequest,
    AttemptState,
    AutosaveRequest,
    BlueprintCreate,
    BlueprintOut,
    ExamDetail,
    ExamOut,
    GenerateExamRequest,
    MarkingOut,
)
from ...security import get_current_user, require_workspace
from ...services import analytics as analytics_service
from ...services import examination as exam_service

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["examinations"])


def _get_examination(db: Session, workspace: SubjectWorkspace,
                     examination_id: str) -> Examination:
    examination = db.get(Examination, examination_id)
    if examination is None or examination.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Examination not found in this workspace")
    return examination


# --------------------------------------------------------------------------
# Blueprints
# --------------------------------------------------------------------------

@router.post("/blueprints", response_model=BlueprintOut, status_code=status.HTTP_201_CREATED)
def create_blueprint(payload: BlueprintCreate,
                     workspace: SubjectWorkspace = Depends(require_workspace),
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> ExaminationBlueprint:
    blueprint = ExaminationBlueprint(
        workspace_id=workspace.id,
        title=payload.title,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks,
        question_count=payload.question_count,
        difficulty=payload.difficulty,
        topic_ids=payload.topic_ids,
        outcome_ids=payload.outcome_ids,
        difficulty_distribution=payload.difficulty_distribution,
        type_distribution=payload.type_distribution,
        bloom_distribution=payload.bloom_distribution,
        required_visual_keys=payload.required_visual_keys,
        assessment_objectives=payload.assessment_objectives,
        instructions=payload.instructions,
    )
    db.add(blueprint)
    db.flush()
    exam_service.validate_blueprint(db, workspace, blueprint)
    db.commit()
    db.refresh(blueprint)
    return blueprint


@router.get("/blueprints", response_model=list[BlueprintOut])
def list_blueprints(workspace: SubjectWorkspace = Depends(require_workspace),
                    db: Session = Depends(get_db)) -> list[ExaminationBlueprint]:
    return list(db.scalars(select(ExaminationBlueprint).where(
        ExaminationBlueprint.workspace_id == workspace.id
    ).order_by(ExaminationBlueprint.created_at.desc())))


@router.get("/blueprints/{blueprint_id}/validate")
def validate_blueprint(blueprint_id: str,
                       workspace: SubjectWorkspace = Depends(require_workspace),
                       db: Session = Depends(get_db)) -> dict:
    blueprint = db.get(ExaminationBlueprint, blueprint_id)
    if blueprint is None or blueprint.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blueprint not found in this workspace")
    result = exam_service.validate_blueprint(db, workspace, blueprint)
    db.commit()
    return result


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

@router.post("/blueprints/{blueprint_id}/generate", response_model=ExamDetail,
             status_code=status.HTTP_201_CREATED)
def generate_examination(blueprint_id: str, payload: GenerateExamRequest,
                         workspace: SubjectWorkspace = Depends(require_workspace),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> ExamDetail:
    blueprint = db.get(ExaminationBlueprint, blueprint_id)
    if blueprint is None or blueprint.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blueprint not found in this workspace")
    try:
        examination = exam_service.generate_examination(
            db, workspace, blueprint, payload.mode, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(examination)
    return _exam_detail(examination, include_answers=True)


@router.get("/examinations", response_model=list[ExamOut])
def list_examinations(workspace: SubjectWorkspace = Depends(require_workspace),
                      db: Session = Depends(get_db)) -> list[Examination]:
    return list(db.scalars(select(Examination).where(
        Examination.workspace_id == workspace.id).order_by(Examination.created_at.desc())))


@router.get("/examinations/{examination_id}", response_model=ExamDetail)
def get_examination(examination_id: str,
                    workspace: SubjectWorkspace = Depends(require_workspace),
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> ExamDetail:
    examination = _get_examination(db, workspace, examination_id)
    return _exam_detail(examination, include_answers=True)


@router.post("/examinations/{examination_id}/moderate")
def moderate_examination(examination_id: str,
                         workspace: SubjectWorkspace = Depends(require_workspace),
                         db: Session = Depends(get_db)) -> dict:
    examination = _get_examination(db, workspace, examination_id)
    result = exam_service.remoderate(db, examination)
    db.commit()
    return {"status": result.status,
            "can_publish": result.can_publish,
            "findings": [f.as_dict() for f in result.findings]}


@router.post("/examinations/{examination_id}/publish", response_model=ExamOut)
def publish_examination(examination_id: str,
                        workspace: SubjectWorkspace = Depends(require_workspace),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> Examination:
    examination = _get_examination(db, workspace, examination_id)
    result = exam_service.remoderate(db, examination)
    if not result.can_publish:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Examination cannot be published: unresolved moderation findings ("
            + ", ".join(sorted({f.code for f in result.findings if f.severity != 'minor'})) + ")")
    examination.status = ExamStatus.PUBLISHED.value
    examination.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(examination)
    return examination


@router.post("/examinations/{examination_id}/release-feedback")
def release_feedback(examination_id: str,
                     workspace: SubjectWorkspace = Depends(require_workspace),
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    examination = _get_examination(db, workspace, examination_id)
    released = exam_service.release_feedback(db, examination, user.id)
    db.commit()
    return {"released_attempts": released}


# --------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------

@router.post("/examinations/{examination_id}/attempts", response_model=AttemptOut,
             status_code=status.HTTP_201_CREATED)
def start_attempt(examination_id: str, payload: AttemptStartRequest,
                  workspace: SubjectWorkspace = Depends(require_workspace),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> ExaminationAttempt:
    examination = _get_examination(db, workspace, examination_id)
    try:
        attempt = exam_service.start_attempt(
            db, examination, user.id, payload.student_name or user.display_name,
            payload.student_number, examination.mode)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    db.refresh(attempt)
    return attempt


def _get_attempt(db: Session, workspace: SubjectWorkspace, attempt_id: str,
                 user: User) -> ExaminationAttempt:
    attempt = db.get(ExaminationAttempt, attempt_id)
    if attempt is None or attempt.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found in this workspace")
    if attempt.student_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This attempt belongs to another student")
    return attempt


@router.get("/attempts/{attempt_id}", response_model=AttemptState)
def get_attempt_state(attempt_id: str,
                      workspace: SubjectWorkspace = Depends(require_workspace),
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> AttemptState:
    attempt = _get_attempt(db, workspace, attempt_id, user)
    examination = _get_examination(db, workspace, attempt.examination_id)
    responses = list(db.scalars(select(StudentResponse).where(
        StudentResponse.attempt_id == attempt.id)))
    now = datetime.now(timezone.utc)
    remaining = None
    if attempt.deadline_at:
        deadline = attempt.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        remaining = max(0, int((deadline - now).total_seconds()))
    if (attempt.status == AttemptStatus.IN_PROGRESS.value and remaining == 0):
        attempt.status = AttemptStatus.EXPIRED.value
        db.commit()
    return AttemptState(
        attempt=AttemptOut.model_validate(attempt),
        examination=ExamOut.model_validate(examination),
        questions=exam_service.public_questions(examination, include_answers=False),
        responses={r.question_id: r.answer for r in responses},
        flags={r.question_id: r.flagged for r in responses},
        server_time=now,
        remaining_seconds=remaining,
    )


@router.put("/attempts/{attempt_id}/responses")
def autosave(attempt_id: str, payload: AutosaveRequest,
             workspace: SubjectWorkspace = Depends(require_workspace),
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    attempt = _get_attempt(db, workspace, attempt_id, user)
    try:
        exam_service.save_responses(db, attempt, [r.model_dump() for r in payload.responses])
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return {"saved": len(payload.responses),
            "server_time": datetime.now(timezone.utc).isoformat()}


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: str,
                   workspace: SubjectWorkspace = Depends(require_workspace),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    attempt = _get_attempt(db, workspace, attempt_id, user)
    try:
        exam_service.submit_attempt(db, attempt, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    db.refresh(attempt)
    examination = _get_examination(db, workspace, attempt.examination_id)
    return {
        "attempt": AttemptOut.model_validate(attempt).model_dump(),
        "feedback_available": attempt.feedback_released,
        "score": attempt.score if attempt.feedback_released else None,
        "max_score": attempt.max_score if attempt.feedback_released else None,
        "percentage": attempt.percentage if attempt.feedback_released else None,
    }


@router.get("/attempts/{attempt_id}/result")
def attempt_result(attempt_id: str,
                   workspace: SubjectWorkspace = Depends(require_workspace),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    attempt = _get_attempt(db, workspace, attempt_id, user)
    examination = _get_examination(db, workspace, attempt.examination_id)
    records = list(db.scalars(select(MarkingRecord).where(
        MarkingRecord.attempt_id == attempt.id)))
    result: dict = {
        "attempt": AttemptOut.model_validate(attempt).model_dump(),
        "markings": [MarkingOut.model_validate(r).model_dump() for r in records],
        "analytics": analytics_service.attempt_analytics(db, attempt, examination),
        "feedback_released": attempt.feedback_released,
    }
    if attempt.feedback_released:
        questions = {q["question_id"]: q for q in (examination.question_snapshot or [])}
        result["memorandum"] = [
            {
                "question_id": r.question_id,
                "prompt": questions.get(r.question_id, {}).get("prompt", ""),
                "expected_answer": questions.get(r.question_id, {}).get("expected_answer", ""),
                "explanation": questions.get(r.question_id, {}).get("explanation", ""),
                "awarded": r.awarded,
                "max_marks": r.max_marks,
                "rationale": r.rationale,
                "breakdown": r.breakdown,
            }
            for r in records
        ]
    return result


@router.post("/markings/{marking_id}/review")
def review_marking(marking_id: str, payload: dict,
                   workspace: SubjectWorkspace = Depends(require_workspace),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    record = db.get(MarkingRecord, marking_id)
    if record is None or record.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Marking record not found")
    awarded = payload.get("awarded")
    if awarded is not None:
        try:
            awarded = float(awarded)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "awarded must be numeric") from exc
        if awarded < 0 or awarded > record.max_marks:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"awarded must be between 0 and {record.max_marks}")
        record.awarded = awarded
    record.reviewed = True
    record.reviewer_id = user.id
    record.needs_human_review = False
    if payload.get("rationale"):
        record.rationale = f"{record.rationale} | Reviewer: {payload['rationale']}"
    db.flush()
    _recalculate_attempt(db, record.attempt_id)
    db.commit()
    return MarkingOut.model_validate(record).model_dump()


def _recalculate_attempt(db: Session, attempt_id: str) -> None:
    attempt = db.get(ExaminationAttempt, attempt_id)
    if attempt is None:
        return
    records = list(db.scalars(select(MarkingRecord).where(
        MarkingRecord.attempt_id == attempt_id)))
    total = sum(r.awarded for r in records)
    max_total = sum(r.max_marks for r in records)
    attempt.score = round(total, 2)
    attempt.max_score = round(max_total, 2)
    attempt.percentage = round(total / max_total * 100, 2) if max_total else 0.0
    db.flush()


# --------------------------------------------------------------------------
# Analytics + PDFs
# --------------------------------------------------------------------------

@router.get("/analytics")
def workspace_analytics(workspace: SubjectWorkspace = Depends(require_workspace),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    return analytics_service.analyse_workspace(db, workspace.id, user.id)


@router.post("/examinations/{examination_id}/deliverables")
def create_deliverables(examination_id: str,
                        workspace: SubjectWorkspace = Depends(require_workspace),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    examination = _get_examination(db, workspace, examination_id)
    deliverables = exam_service.generate_deliverables(db, examination, user.id)
    db.commit()
    return deliverables


@router.get("/examinations/{examination_id}/deliverables")
def list_deliverables(examination_id: str,
                      workspace: SubjectWorkspace = Depends(require_workspace),
                      db: Session = Depends(get_db)) -> list[dict]:
    examination = _get_examination(db, workspace, examination_id)
    return [
        {"id": d.id, "kind": d.kind, "version": d.exam_version, "released": d.released,
         "content_hash": d.content_hash,
         "created_at": d.created_at.isoformat()}
        for d in db.scalars(select(PDFDeliverable).where(
            PDFDeliverable.examination_id == examination.id))
    ]


@router.get("/examinations/{examination_id}/deliverables/{kind}/download")
def download_deliverable(examination_id: str, kind: str,
                         workspace: SubjectWorkspace = Depends(require_workspace),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> FileResponse:
    examination = _get_examination(db, workspace, examination_id)
    if kind not in {PDFKind.MEMORANDUM.value, PDFKind.MASTERY_GUIDE.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown deliverable kind")
    deliverable = db.scalars(select(PDFDeliverable).where(
        PDFDeliverable.examination_id == examination.id,
        PDFDeliverable.kind == kind,
        PDFDeliverable.exam_version == examination.version)).first()
    if deliverable is None:
        deliverables = exam_service.generate_deliverables(db, examination, user.id)
        db.commit()
        deliverable = db.scalars(select(PDFDeliverable).where(
            PDFDeliverable.examination_id == examination.id,
            PDFDeliverable.kind == kind,
            PDFDeliverable.exam_version == examination.version)).first()
        if deliverable is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                "Deliverable could not be generated")
    # Formal memoranda are protected until authorised release.
    if kind == PDFKind.MEMORANDUM.value and not deliverable.released:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The memorandum for this formal examination has not been released yet")
    filename = (f"{examination.subject_name or 'examination'}"
                f"-{kind}-v{examination.version}.pdf").replace(" ", "_")
    return FileResponse(deliverable.path, media_type="application/pdf", filename=filename)


def _exam_detail(examination: Examination, include_answers: bool) -> ExamDetail:
    return ExamDetail(
        id=examination.id,
        title=examination.title,
        subject_name=examination.subject_name,
        module_name=examination.module_name,
        version=examination.version,
        mode=examination.mode,
        status=examination.status,
        duration_minutes=examination.duration_minutes,
        total_marks=examination.total_marks,
        instructions=examination.instructions,
        sections=examination.sections or [],
        moderation_status=examination.moderation_status,
        moderation_findings=examination.moderation_findings or [],
        published_at=examination.published_at,
        questions=exam_service.public_questions(examination, include_answers=include_answers),
    )
