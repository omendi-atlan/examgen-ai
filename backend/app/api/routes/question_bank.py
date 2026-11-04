"""Private student question-bank generation and retrieval endpoints."""

import hashlib
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_workspace_membership, limit_question_generation_attempts
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AcademicDocument,
    DocumentExtraction,
    DocumentVersion,
    ExtractionStatus,
    LearningOutcome,
    Question,
    QuestionReviewStatus,
    QuestionVersion,
    Subject,
    Topic,
    WorkspaceMembership,
)
from app.schemas.questions import (
    QuestionCitation,
    QuestionGenerationRequest,
    QuestionGenerationResponse,
    QuestionResponse,
    QuestionVersionResponse,
)
from app.services.audit import record_audit_event
from app.services.question_generation import (
    QUESTION_PROMPT_VERSION,
    QuestionProviderInvalidOutput,
    QuestionProviderUnavailable,
    build_generation_prompt,
    generate_question_payload,
)

router = APIRouter(tags=["question-bank"])
DatabaseSession = Annotated[Session, Depends(get_db)]
ActiveMember = Annotated[WorkspaceMembership, Depends(get_workspace_membership)]


def _subject(db: Session, workspace_id: UUID, subject_id: UUID) -> Subject:
    subject = db.scalar(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    return subject


def _question_response(question: Question) -> QuestionResponse:
    versions = []
    for version in question.versions:
        versions.append(
            QuestionVersionResponse(
                id=version.id,
                version_number=version.version_number,
                question_type=version.question_type,
                stem=version.stem,
                options=version.options,
                marks=version.marks,
                difficulty=version.difficulty,
                cognitive_level=version.cognitive_level,
                topic_id=version.topic_id,
                learning_outcome_id=version.learning_outcome_id,
                source_citations=[QuestionCitation.model_validate(item) for item in version.source_citations],
                review_status=version.review_status.value
                if isinstance(version.review_status, QuestionReviewStatus)
                else str(version.review_status),
            )
        )
    return QuestionResponse(
        id=question.id,
        subject_id=question.subject_id,
        current_version_number=question.current_version_number,
        created_at=question.created_at.isoformat(),
        versions=versions,
    )


def _load_questions(
    db: Session,
    workspace_id: UUID,
    subject_id: UUID,
    user_id: UUID,
) -> Sequence[Question]:
    return db.scalars(
        select(Question)
        .where(
            Question.workspace_id == workspace_id,
            Question.subject_id == subject_id,
            Question.created_by == user_id,
        )
        .options(selectinload(Question.versions))
        .order_by(Question.created_at.desc())
        .limit(100)
    ).all()


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/questions/generate",
    response_model=QuestionGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_question_generation_attempts)],
)
async def generate_subject_questions(
    workspace_id: UUID,
    subject_id: UUID,
    payload: QuestionGenerationRequest,
    db: DatabaseSession,
    membership: ActiveMember,
) -> QuestionGenerationResponse:
    """Generate source-cited private questions from the student's own extracted material."""
    _subject(db, workspace_id, subject_id)
    settings = get_settings()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise HTTPException(
            status_code=503,
            detail="Question generation is not configured. Contact the platform administrator.",
        )

    if payload.topic_id is not None:
        topic = db.scalar(
            select(Topic).where(
                Topic.id == payload.topic_id,
                Topic.workspace_id == workspace_id,
                Topic.subject_id == subject_id,
            )
        )
        if topic is None:
            raise HTTPException(status_code=422, detail="Selected topic is outside this subject.")
    if payload.learning_outcome_id is not None:
        outcome = db.scalar(
            select(LearningOutcome)
            .join(Topic, Topic.id == LearningOutcome.topic_id)
            .where(
                LearningOutcome.id == payload.learning_outcome_id,
                LearningOutcome.workspace_id == workspace_id,
                Topic.workspace_id == workspace_id,
                Topic.subject_id == subject_id,
            )
        )
        if outcome is None:
            raise HTTPException(
                status_code=422,
                detail="Selected learning outcome is outside this subject.",
            )

    visible_source = or_(
        AcademicDocument.created_by == membership.user_id,
        and_(
            AcademicDocument.visibility == "cohort",
            Subject.resource_sharing_enabled.is_(True),
        ),
    )
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .join(AcademicDocument, AcademicDocument.id == DocumentVersion.document_id)
            .join(Subject, Subject.id == AcademicDocument.subject_id)
            .join(DocumentExtraction, DocumentExtraction.version_id == DocumentVersion.id)
            .where(
                DocumentVersion.id.in_(payload.source_version_ids),
                AcademicDocument.workspace_id == workspace_id,
                AcademicDocument.subject_id == subject_id,
                visible_source,
                DocumentExtraction.status == ExtractionStatus.EXTRACTED,
            )
            .options(
                selectinload(DocumentVersion.document),
                selectinload(DocumentVersion.extraction).selectinload(DocumentExtraction.segments),
            )
        ).all()
    )
    if len(versions) != len(payload.source_version_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more selected source versions are unavailable, private or not fully extracted.",
        )

    source_segments: list[dict[str, object]] = []
    citation_index: dict[UUID, dict[str, object]] = {}
    for version in versions:
        document = version.document
        extraction = version.extraction
        if extraction is None or not extraction.segments:
            continue
        for segment in extraction.segments:
            source_segments.append(
                {
                    "segment_id": str(segment.id),
                    "locator": segment.locator,
                    "text": segment.text,
                }
            )
            citation_index[segment.id] = {
                "document_title": document.title,
                "original_filename": version.original_filename,
                "version_number": version.version_number,
                "locator": segment.locator,
                "segment_id": segment.id,
                "source_version_id": str(version.id),
            }
    if not source_segments:
        raise HTTPException(status_code=422, detail="Selected sources contain no usable extracted text.")

    try:
        prompt = build_generation_prompt(payload, source_segments)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None

    try:
        generated = await generate_question_payload(
            prompt=prompt,
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=settings.question_generation_timeout_seconds,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Question generation timed out. Please retry.") from None
    except QuestionProviderUnavailable:
        raise HTTPException(status_code=503, detail="The question-generation provider is temporarily unavailable.") from None
    except QuestionProviderInvalidOutput:
        raise HTTPException(status_code=422, detail="Generated questions failed schema validation. Please retry.") from None

    questions = generated.questions
    if len(questions) != payload.question_count:
        raise HTTPException(status_code=422, detail="Generated question count did not match the request.")
    if sum(item.marks for item in questions) != payload.total_marks:
        raise HTTPException(status_code=422, detail="Generated question marks did not match the requested total.")
    if any(item.question_type not in payload.question_types for item in questions):
        raise HTTPException(status_code=422, detail="Generated output contains an unrequested question type.")
    if any(item.difficulty != payload.difficulty for item in questions):
        raise HTTPException(status_code=422, detail="Generated output contains an unrequested difficulty.")
    if any(item.cognitive_level not in payload.cognitive_levels for item in questions):
        raise HTTPException(status_code=422, detail="Generated output contains an unrequested cognitive level.")
    if any(
        not set(item.source_segment_ids) <= set(citation_index)
        for item in questions
    ):
        raise HTTPException(status_code=422, detail="Generated output cites a source passage that was not supplied.")

    created: list[Question] = []
    fingerprints: set[str] = set()
    try:
        for item in questions:
            normalized_stem = " ".join(item.stem.casefold().split())
            fingerprint = hashlib.sha256(f"{item.question_type}:{normalized_stem}".encode()).hexdigest()
            if fingerprint in fingerprints or db.scalar(
                select(Question.id).where(
                    Question.workspace_id == workspace_id,
                    Question.subject_id == subject_id,
                    Question.created_by == membership.user_id,
                    Question.fingerprint == fingerprint,
                )
            ) is not None:
                raise HTTPException(status_code=409, detail="Generated questions duplicate an existing question in your subject bank.")
            fingerprints.add(fingerprint)
            citations = [citation_index[source_id] for source_id in item.source_segment_ids]
            question = Question(
                workspace_id=workspace_id,
                subject_id=subject_id,
                created_by=membership.user_id,
                current_version_number=0,
                fingerprint=fingerprint,
            )
            db.add(question)
            db.flush()
            version = QuestionVersion(
                question_id=question.id,
                version_number=1,
                topic_id=payload.topic_id,
                learning_outcome_id=payload.learning_outcome_id,
                question_type=item.question_type,
                stem=item.stem,
                options=item.options,
                correct_answer=item.correct_answer,
                explanation=item.explanation,
                marks=item.marks,
                difficulty=item.difficulty,
                cognitive_level=item.cognitive_level,
                source_citations=citations,
                generation_model=settings.openai_model,
                prompt_version=QUESTION_PROMPT_VERSION,
                review_status=QuestionReviewStatus.DRAFT,
            )
            db.add(version)
            db.flush()
            question.current_version_number = 1
            record_audit_event(
                db,
                action="question_bank.question_generated",
                resource_type="question",
                resource_id=str(question.id),
                actor_user_id=membership.user_id,
                workspace_id=workspace_id,
                event_data={
                    "subject_id": str(subject_id),
                    "question_version_id": str(version.id),
                    "question_type": item.question_type,
                    "marks": item.marks,
                    "source_version_ids": [str(citation["source_version_id"]) for citation in citations],
                    "review_status": QuestionReviewStatus.DRAFT.value,
                },
            )
            created.append(question)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Generated question records could not be saved because of a duplicate or concurrent update.") from None
    except HTTPException:
        db.rollback()
        raise

    saved = list(
        db.scalars(
            select(Question)
            .where(Question.id.in_([item.id for item in created]))
            .options(selectinload(Question.versions))
            .order_by(Question.created_at, Question.id)
        ).all()
    )
    return QuestionGenerationResponse(
        created_count=len(saved),
        total_marks=sum(item.marks for item in questions),
        questions=[_question_response(item) for item in saved],
    )


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/questions",
    response_model=list[QuestionResponse],
)
def list_my_subject_questions(
    workspace_id: UUID,
    subject_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> list[QuestionResponse]:
    """List only the authenticated student's own question-bank records."""
    _subject(db, workspace_id, subject_id)
    return [
        _question_response(item)
        for item in _load_questions(db, workspace_id, subject_id, membership.user_id)
    ]
