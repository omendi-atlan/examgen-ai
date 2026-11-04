"""Timed practice exams with immutable question snapshots and durable submissions."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_workspace_membership
from app.core.database import get_db
from app.models import (
    PracticeAttempt,
    PracticeAttemptResponse,
    PracticeAttemptStatus,
    PracticeExam,
    PracticeExamQuestion,
    Question,
    QuestionVersion,
    WorkspaceMembership,
)
from app.schemas.practice import (
    PracticeAttemptQuestionResponse,
    PracticeAttemptResponseModel,
    PracticeAttemptSaveRequest,
    PracticeExamCreateRequest,
    PracticeExamResponse,
)
from app.services.audit import record_audit_event

router = APIRouter(tags=["practice-examinations"])
DatabaseSession = Annotated[Session, Depends(get_db)]
ActiveMember = Annotated[WorkspaceMembership, Depends(get_workspace_membership)]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _exam_response(exam: PracticeExam) -> PracticeExamResponse:
    return PracticeExamResponse(
        id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        question_count=exam.question_count,
        created_at=exam.created_at,
    )


def _load_exam(
    db: Session,
    workspace_id: UUID,
    subject_id: UUID,
    exam_id: UUID,
    user_id: UUID,
) -> PracticeExam:
    exam = db.scalar(
        select(PracticeExam)
        .where(
            PracticeExam.id == exam_id,
            PracticeExam.workspace_id == workspace_id,
            PracticeExam.subject_id == subject_id,
            PracticeExam.created_by == user_id,
        )
        .options(
            selectinload(PracticeExam.questions).selectinload(
                PracticeExamQuestion.question_version
            )
        )
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Practice examination not found.")
    return exam


def _load_attempt(
    db: Session,
    workspace_id: UUID,
    subject_id: UUID,
    attempt_id: UUID,
    user_id: UUID,
    *,
    lock: bool = False,
) -> PracticeAttempt:
    statement = (
        select(PracticeAttempt)
        .join(PracticeExam, PracticeExam.id == PracticeAttempt.exam_id)
        .where(
            PracticeAttempt.id == attempt_id,
            PracticeAttempt.student_id == user_id,
            PracticeExam.workspace_id == workspace_id,
            PracticeExam.subject_id == subject_id,
        )
        .options(
            selectinload(PracticeAttempt.exam)
            .selectinload(PracticeExam.questions)
            .selectinload(PracticeExamQuestion.question_version),
            selectinload(PracticeAttempt.responses),
        )
    )
    if lock:
        statement = statement.with_for_update()
    attempt = db.scalar(statement)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Practice attempt not found.")
    return attempt


def _attempt_response(attempt: PracticeAttempt) -> PracticeAttemptResponseModel:
    finalised = attempt.status in {
        PracticeAttemptStatus.SUBMITTED,
        PracticeAttemptStatus.EXPIRED,
    }
    saved = {item.exam_question_id: item for item in attempt.responses}
    questions = []
    for exam_question in attempt.exam.questions:
        version = exam_question.question_version
        response = saved.get(exam_question.id)
        questions.append(
            PracticeAttemptQuestionResponse(
                exam_question_id=exam_question.id,
                question_version_id=version.id,
                ordinal=exam_question.ordinal,
                question_type=version.question_type,
                stem=version.stem,
                options=version.options,
                marks=exam_question.marks,
                response=response.response if response else None,
                marking_status=response.marking_status if response else "unanswered",
                awarded_marks=response.awarded_marks if response else None,
                is_correct=response.is_correct if response else None,
                correct_answer=version.correct_answer if finalised else None,
                explanation=version.explanation if finalised else None,
            )
        )
    return PracticeAttemptResponseModel(
        id=attempt.id,
        exam_id=attempt.exam_id,
        exam_title=attempt.exam.title,
        status=attempt.status.value if isinstance(attempt.status, PracticeAttemptStatus) else str(attempt.status),
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        submitted_at=attempt.submitted_at,
        total_marks=attempt.exam.total_marks,
        awarded_marks=attempt.awarded_marks,
        pending_review_count=attempt.pending_review_count,
        questions=questions,
    )


def _objective_score(
    question_type: str,
    correct_answer: dict[str, object],
    response: dict[str, object],
) -> bool | None:
    """Return deterministic objective correctness, or None for rubric/human marking."""
    if question_type in {"multiple_choice", "true_false"}:
        expected = correct_answer.get("option_id")
        actual = response.get("option_id")
        return isinstance(expected, str) and actual == expected
    if question_type == "multiple_select":
        expected = correct_answer.get("option_ids")
        actual = response.get("option_ids")
        if not isinstance(expected, list) or not isinstance(actual, list):
            return False
        return set(str(item) for item in expected) == set(str(item) for item in actual)
    if question_type == "fill_blank":
        expected = correct_answer.get("accepted_answers")
        actual = response.get("text")
        if not isinstance(expected, list) or not isinstance(actual, str):
            return False
        normalised = " ".join(actual.casefold().split())
        return normalised in {" ".join(str(item).casefold().split()) for item in expected}
    if question_type == "numeric":
        expected = correct_answer.get("value")
        actual = response.get("value")
        tolerance = correct_answer.get("tolerance", 0)
        if isinstance(expected, bool) or not isinstance(expected, (int, float)):
            return False
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return False
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            tolerance = 0
        return abs(float(actual) - float(expected)) <= float(tolerance)
    return None


def _finalise_attempt(
    db: Session,
    attempt: PracticeAttempt,
    *,
    now: datetime,
) -> None:
    saved = {item.exam_question_id: item for item in attempt.responses}
    awarded_total = 0
    pending_review = 0
    for exam_question in attempt.exam.questions:
        version = exam_question.question_version
        response_record = saved.get(exam_question.id)
        if response_record is None:
            response_record = PracticeAttemptResponse(
                attempt_id=attempt.id,
                exam_question_id=exam_question.id,
                response={},
            )
            db.add(response_record)
            saved[exam_question.id] = response_record

        if not response_record.response:
            response_record.awarded_marks = 0
            response_record.is_correct = False if version.question_type in {
                "multiple_choice", "multiple_select", "true_false", "fill_blank", "numeric"
            } else None
            response_record.marking_status = "unanswered"
            continue

        is_correct = _objective_score(
            version.question_type,
            version.correct_answer,
            response_record.response,
        )
        if is_correct is None:
            response_record.awarded_marks = None
            response_record.is_correct = None
            response_record.marking_status = "pending_review"
            pending_review += 1
        else:
            response_record.is_correct = is_correct
            response_record.awarded_marks = exam_question.marks if is_correct else 0
            response_record.marking_status = "marked"
            awarded_total += response_record.awarded_marks

    attempt.awarded_marks = awarded_total
    attempt.pending_review_count = pending_review
    attempt.submitted_at = now
    attempt.status = (
        PracticeAttemptStatus.EXPIRED
        if now >= _as_utc(attempt.expires_at)
        else PracticeAttemptStatus.SUBMITTED
    )
    record_audit_event(
        db,
        action="practice_attempt.expired" if attempt.status == PracticeAttemptStatus.EXPIRED else "practice_attempt.submitted",
        resource_type="practice_attempt",
        resource_id=str(attempt.id),
        actor_user_id=attempt.student_id,
        workspace_id=attempt.exam.workspace_id,
        event_data={
            "exam_id": str(attempt.exam_id),
            "awarded_marks": awarded_total,
            "total_marks": attempt.exam.total_marks,
            "pending_review_count": pending_review,
            "status": attempt.status.value,
        },
    )


def _validate_response(question_type: str, response: dict[str, object]) -> None:
    if len(json.dumps(response, ensure_ascii=False)) > 20000:
        raise HTTPException(status_code=413, detail="Response exceeds the permitted size.")
    if question_type in {"multiple_choice", "true_false"}:
        if "option_id" in response and not isinstance(response["option_id"], str):
            raise HTTPException(status_code=422, detail="Select one valid answer option.")
    elif question_type == "multiple_select":
        values = response.get("option_ids", [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise HTTPException(status_code=422, detail="Multiple-select response must contain option identifiers.")
    elif question_type == "fill_blank":
        if "text" in response and not isinstance(response["text"], str):
            raise HTTPException(status_code=422, detail="Fill-in response must be text.")
    elif question_type == "numeric":
        value = response.get("value")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise HTTPException(status_code=422, detail="Numeric response must be a number.")


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-exams",
    response_model=PracticeExamResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_practice_exam(
    workspace_id: UUID,
    subject_id: UUID,
    payload: PracticeExamCreateRequest,
    db: DatabaseSession,
    membership: ActiveMember,
) -> PracticeExamResponse:
    """Freeze selected question versions into a private practice examination."""
    versions = list(
        db.scalars(
            select(QuestionVersion)
            .join(Question, Question.id == QuestionVersion.question_id)
            .where(
                QuestionVersion.id.in_(payload.question_version_ids),
                Question.workspace_id == workspace_id,
                Question.subject_id == subject_id,
                Question.created_by == membership.user_id,
            )
        ).all()
    )
    if len(versions) != len(payload.question_version_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more selected questions are unavailable in your subject bank.",
        )
    by_id = {item.id: item for item in versions}
    ordered = [by_id[item] for item in payload.question_version_ids]
    total_marks = sum(item.marks for item in ordered)
    if total_marks > 1000:
        raise HTTPException(status_code=422, detail="Practice exam total marks cannot exceed 1,000.")
    exam = PracticeExam(
        workspace_id=workspace_id,
        subject_id=subject_id,
        created_by=membership.user_id,
        title=payload.title,
        duration_minutes=payload.duration_minutes,
        total_marks=total_marks,
        question_count=len(ordered),
    )
    db.add(exam)
    db.flush()
    db.add_all(
        [
            PracticeExamQuestion(
                exam_id=exam.id,
                question_version_id=version.id,
                ordinal=index,
                marks=version.marks,
            )
            for index, version in enumerate(ordered, start=1)
        ]
    )
    record_audit_event(
        db,
        action="practice_exam.created",
        resource_type="practice_exam",
        resource_id=str(exam.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={
            "subject_id": str(subject_id),
            "question_count": exam.question_count,
            "total_marks": exam.total_marks,
            "duration_minutes": exam.duration_minutes,
        },
    )
    db.commit()
    return _exam_response(exam)


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-exams",
    response_model=list[PracticeExamResponse],
)
def list_practice_exams(
    workspace_id: UUID,
    subject_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> list[PracticeExamResponse]:
    exams = db.scalars(
        select(PracticeExam)
        .where(
            PracticeExam.workspace_id == workspace_id,
            PracticeExam.subject_id == subject_id,
            PracticeExam.created_by == membership.user_id,
        )
        .order_by(PracticeExam.created_at.desc())
    ).all()
    return [_exam_response(item) for item in exams]


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-exams/{exam_id}/attempts",
    response_model=PracticeAttemptResponseModel,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def start_practice_attempt(
    workspace_id: UUID,
    subject_id: UUID,
    exam_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> PracticeAttemptResponseModel:
    exam = _load_exam(db, workspace_id, subject_id, exam_id, membership.user_id)
    now = datetime.now(UTC)
    attempt = PracticeAttempt(
        exam_id=exam.id,
        student_id=membership.user_id,
        status=PracticeAttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=now + timedelta(minutes=exam.duration_minutes),
        awarded_marks=0,
        pending_review_count=0,
    )
    db.add(attempt)
    db.flush()
    record_audit_event(
        db,
        action="practice_attempt.started",
        resource_type="practice_attempt",
        resource_id=str(attempt.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"exam_id": str(exam.id), "expires_at": attempt.expires_at.isoformat()},
    )
    db.commit()
    attempt = _load_attempt(db, workspace_id, subject_id, attempt.id, membership.user_id)
    return _attempt_response(attempt)


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-attempts/{attempt_id}",
    response_model=PracticeAttemptResponseModel,
    response_model_exclude_none=True,
)
def get_practice_attempt(
    workspace_id: UUID,
    subject_id: UUID,
    attempt_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> PracticeAttemptResponseModel:
    attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id, lock=True)
    if attempt.status == PracticeAttemptStatus.IN_PROGRESS and datetime.now(UTC) >= _as_utc(attempt.expires_at):
        _finalise_attempt(db, attempt, now=datetime.now(UTC))
        db.commit()
        attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id)
    return _attempt_response(attempt)


@router.put(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-attempts/{attempt_id}/responses/{exam_question_id}",
    response_model=PracticeAttemptResponseModel,
)
def save_practice_response(
    workspace_id: UUID,
    subject_id: UUID,
    attempt_id: UUID,
    exam_question_id: UUID,
    payload: PracticeAttemptSaveRequest,
    db: DatabaseSession,
    membership: ActiveMember,
) -> PracticeAttemptResponseModel:
    attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id, lock=True)
    now = datetime.now(UTC)
    if attempt.status != PracticeAttemptStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="This practice attempt is already finalised.")
    if now >= _as_utc(attempt.expires_at):
        _finalise_attempt(db, attempt, now=now)
        db.commit()
        raise HTTPException(status_code=409, detail="The practice attempt time has expired and the attempt was finalised.")

    exam_question = next(
        (item for item in attempt.exam.questions if item.id == exam_question_id),
        None,
    )
    if exam_question is None:
        raise HTTPException(status_code=404, detail="Question is not part of this practice attempt.")
    _validate_response(exam_question.question_version.question_type, payload.response)

    saved = next(
        (item for item in attempt.responses if item.exam_question_id == exam_question_id),
        None,
    )
    if saved is None:
        saved = PracticeAttemptResponse(
            attempt_id=attempt.id,
            exam_question_id=exam_question_id,
            response=payload.response,
            marking_status="saved",
        )
        db.add(saved)
    else:
        saved.response = payload.response
        saved.marking_status = "saved"
    db.commit()
    attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id)
    return _attempt_response(attempt)


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/practice-attempts/{attempt_id}/submit",
    response_model=PracticeAttemptResponseModel,
)
def submit_practice_attempt(
    workspace_id: UUID,
    subject_id: UUID,
    attempt_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> PracticeAttemptResponseModel:
    attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id, lock=True)
    if attempt.status == PracticeAttemptStatus.IN_PROGRESS:
        _finalise_attempt(db, attempt, now=datetime.now(UTC))
        db.commit()
        attempt = _load_attempt(db, workspace_id, subject_id, attempt_id, membership.user_id)
    return _attempt_response(attempt)
