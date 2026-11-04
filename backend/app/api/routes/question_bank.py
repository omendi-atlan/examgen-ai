"""Workspace-authorised question bank, provenance and blueprint-driven generation."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    enforce_auth_rate_limit,
    get_workspace_membership,
    require_workspace_roles,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AcademicDocument,
    BlueprintVersionStatus,
    DocumentExtraction,
    DocumentExtractionReview,
    DocumentTextSegment,
    DocumentVersion,
    ExamBlueprint,
    ExamBlueprintVersion,
    ExtractionStatus,
    LearningOutcome,
    MembershipRole,
    Question,
    QuestionSourceCitation,
    QuestionVersion,
    QuestionVersionStatus,
    Subject,
    Topic,
    WorkspaceMembership,
)
from app.schemas.question_bank import (
    QuestionAuthoringResponse,
    QuestionContentInput,
    QuestionCreate,
    QuestionGenerationRequest,
    QuestionGenerationResponse,
    QuestionResponse,
    QuestionSourceCitationResponse,
    QuestionVersionAppend,
    QuestionVersionAuthoringResponse,
    QuestionVersionPublicResponse,
)
from app.services.audit import record_audit_event
from app.services.question_generation import QuestionGenerationError, QuestionGenerationService

router = APIRouter(tags=["question-bank"])
DatabaseSession = Annotated[Session, Depends(get_db)]
ActiveMember = Annotated[WorkspaceMembership, Depends(get_workspace_membership)]
StaffMember = Annotated[
    WorkspaceMembership,
    Depends(
        require_workspace_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.EXAMINER,
            MembershipRole.MODERATOR,
        )
    ),
]


def get_question_generation_service() -> QuestionGenerationService:
    return QuestionGenerationService(get_settings())


QuestionGenerator = Annotated[
    QuestionGenerationService, Depends(get_question_generation_service)
]


def _is_staff(membership: WorkspaceMembership) -> bool:
    return membership.role in {
        MembershipRole.OWNER,
        MembershipRole.ADMIN,
        MembershipRole.EXAMINER,
        MembershipRole.MODERATOR,
    }


def _load_question(db: Session, workspace_id: UUID, question_id: UUID) -> Question:
    question = db.scalar(
        select(Question)
        .where(Question.id == question_id, Question.workspace_id == workspace_id)
        .options(
            selectinload(Question.versions).selectinload(QuestionVersion.citations)
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    return question


def _current_version(question: Question) -> QuestionVersion:
    for version in question.versions:
        if version.version_number == question.current_version_number:
            return version
    raise HTTPException(status_code=409, detail="The question's current version is unavailable.")


def _citation_response(citation: QuestionSourceCitation) -> QuestionSourceCitationResponse:
    return QuestionSourceCitationResponse(
        id=citation.id,
        source_segment_id=citation.source_segment_id,
        source_version_id=citation.source_version_id,
        source_locator=citation.source_locator,
        excerpt=citation.excerpt,
        relevance_note=citation.relevance_note,
    )


def _public_version(version: QuestionVersion) -> QuestionVersionPublicResponse:
    return QuestionVersionPublicResponse(
        id=version.id,
        version_number=version.version_number,
        topic_id=version.topic_id,
        learning_outcome_id=version.learning_outcome_id,
        question_type=version.question_type,
        prompt=version.prompt,
        marks=version.marks,
        cognitive_level=version.cognitive_level,
        difficulty=version.difficulty,
        response_schema=version.response_schema,
        status=version.status.value if isinstance(version.status, QuestionVersionStatus) else version.status,
        citations=[_citation_response(item) for item in version.citations],
    )


def _authoring_version(version: QuestionVersion) -> QuestionVersionAuthoringResponse:
    public = _public_version(version)
    return QuestionVersionAuthoringResponse(
        **public.model_dump(),
        answer_key=version.answer_key,
        model_answer=version.model_answer,
        explanation=version.explanation,
        rubric=version.rubric,
        visual_requirement=version.visual_requirement,
        generation_method=version.generation_method,
        generation_model=version.generation_model,
        content_fingerprint=version.content_fingerprint,
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
    )


def _public_question(question: Question) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        workspace_id=question.workspace_id,
        subject_id=question.subject_id,
        created_by=question.created_by,
        visibility=question.visibility,
        current_version_number=question.current_version_number,
        created_at=question.created_at,
        updated_at=question.updated_at,
        versions=[_public_version(_current_version(question))],
    )


def _authoring_question(question: Question) -> QuestionAuthoringResponse:
    return QuestionAuthoringResponse(
        id=question.id,
        workspace_id=question.workspace_id,
        subject_id=question.subject_id,
        created_by=question.created_by,
        visibility=question.visibility,
        current_version_number=question.current_version_number,
        created_at=question.created_at,
        updated_at=question.updated_at,
        versions=[_authoring_version(item) for item in question.versions],
    )


def _question_fingerprint(
    *, topic_id: UUID, learning_outcome_id: UUID, content: QuestionContentInput
) -> str:
    canonical = {
        "topic_id": str(topic_id),
        "learning_outcome_id": str(learning_outcome_id),
        "question_type": content.question_type,
        "prompt": content.prompt,
        "marks": content.marks,
        "cognitive_level": content.cognitive_level,
        "difficulty": content.difficulty,
        "response_schema": content.response_schema,
        "answer_key": content.answer_key,
        "model_answer": content.model_answer,
        "rubric": content.rubric,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_taxonomy(
    db: Session, workspace_id: UUID, subject_id: UUID, topic_id: UUID, outcome_id: UUID
) -> None:
    topic = db.scalar(
        select(Topic).where(
            Topic.id == topic_id,
            Topic.workspace_id == workspace_id,
            Topic.subject_id == subject_id,
        )
    )
    outcome = db.scalar(
        select(LearningOutcome).where(
            LearningOutcome.id == outcome_id,
            LearningOutcome.workspace_id == workspace_id,
            LearningOutcome.topic_id == topic_id,
        )
    )
    if topic is None or outcome is None:
        raise HTTPException(
            status_code=422,
            detail="The selected topic and learning outcome must belong to the question's subject and workspace.",
        )


def _load_citation_segments(
    *,
    db: Session,
    workspace_id: UUID,
    subject_id: UUID,
    segment_ids: list[UUID],
    membership: WorkspaceMembership,
    visibility: str,
) -> dict[UUID, tuple[DocumentTextSegment, DocumentVersion]]:
    if not segment_ids or len(segment_ids) != len(set(segment_ids)):
        raise HTTPException(status_code=422, detail="Each question must cite unique source segments.")
    rows = db.execute(
        select(DocumentTextSegment, DocumentVersion, AcademicDocument, Subject)
        .join(DocumentExtraction, DocumentExtraction.id == DocumentTextSegment.extraction_id)
        .join(DocumentVersion, DocumentVersion.id == DocumentExtraction.version_id)
        .join(AcademicDocument, AcademicDocument.id == DocumentVersion.document_id)
        .join(Subject, Subject.id == AcademicDocument.subject_id)
        .where(
            DocumentTextSegment.id.in_(segment_ids),
            AcademicDocument.workspace_id == workspace_id,
            AcademicDocument.subject_id == subject_id,
            Subject.workspace_id == workspace_id,
            DocumentExtraction.status == ExtractionStatus.EXTRACTED,
        )
    ).all()
    if len(rows) != len(segment_ids):
        raise HTTPException(
            status_code=422,
            detail="Every citation must reference an extracted segment from this subject.",
        )
    result: dict[UUID, tuple[DocumentTextSegment, DocumentVersion]] = {}
    for segment, version, document, subject in rows:
        owner_access = document.created_by == membership.user_id
        cohort_access = document.visibility == "cohort" and subject.resource_sharing_enabled
        staff_access = _is_staff(membership)
        if not (owner_access or cohort_access or staff_access):
            raise HTTPException(status_code=404, detail="A cited coursework source is not accessible.")
        if visibility == "cohort" and not cohort_access:
            raise HTTPException(
                status_code=409,
                detail="Cohort questions may cite only resources explicitly shared with the subject.",
            )
        latest_review = db.scalar(
            select(DocumentExtractionReview)
            .where(DocumentExtractionReview.version_id == version.id)
            .order_by(DocumentExtractionReview.created_at.desc(), DocumentExtractionReview.id.desc())
            .limit(1)
        )
        if latest_review is not None and latest_review.decision == "rejected":
            raise HTTPException(
                status_code=409,
                detail="A rejected extraction cannot be used as question-bank source material.",
            )
        result[segment.id] = (segment, version)
    return result


def _append_question_version(
    *,
    db: Session,
    question: Question,
    topic_id: UUID,
    learning_outcome_id: UUID,
    content: QuestionContentInput,
    citations: dict[UUID, tuple[DocumentTextSegment, DocumentVersion]],
    actor_user_id: UUID,
    generation_method: str = "manual",
    generation_model: str | None = None,
) -> QuestionVersion:
    fingerprint = _question_fingerprint(
        topic_id=topic_id, learning_outcome_id=learning_outcome_id, content=content
    )
    duplicate = db.scalar(
        select(QuestionVersion.id)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(
            Question.workspace_id == question.workspace_id,
            QuestionVersion.content_fingerprint == fingerprint,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="An equivalent question already exists in this workspace.")

    number = question.current_version_number + 1
    version = QuestionVersion(
        question_id=question.id,
        version_number=number,
        topic_id=topic_id,
        learning_outcome_id=learning_outcome_id,
        question_type=content.question_type,
        prompt=content.prompt,
        marks=content.marks,
        cognitive_level=content.cognitive_level,
        difficulty=content.difficulty,
        response_schema=content.response_schema,
        answer_key=content.answer_key,
        model_answer=content.model_answer,
        explanation=content.explanation,
        rubric=content.rubric,
        visual_requirement=content.visual_requirement,
        generation_method=generation_method,
        generation_model=generation_model,
        content_fingerprint=fingerprint,
        status=QuestionVersionStatus.DRAFT,
        created_by=actor_user_id,
    )
    db.add(version)
    db.flush()
    for segment_id in content.source_segment_ids:
        segment, source_version = citations[segment_id]
        db.add(
            QuestionSourceCitation(
                question_version_id=version.id,
                source_segment_id=segment.id,
                source_version_id=source_version.id,
                source_locator=segment.locator,
                excerpt=segment.text[:1200],
                relevance_note=None,
            )
        )
    question.current_version_number = number
    return version


def _can_view_question(
    db: Session, question: Question, membership: WorkspaceMembership
) -> bool:
    if _is_staff(membership) or question.created_by == membership.user_id:
        return True
    if question.visibility != "cohort":
        return False
    try:
        current = _current_version(question)
    except HTTPException:
        return False
    if current.status != QuestionVersionStatus.APPROVED:
        return False
    inaccessible_source = db.scalar(
        select(QuestionSourceCitation.id)
        .join(DocumentVersion, DocumentVersion.id == QuestionSourceCitation.source_version_id)
        .join(AcademicDocument, AcademicDocument.id == DocumentVersion.document_id)
        .join(Subject, Subject.id == AcademicDocument.subject_id)
        .where(
            QuestionSourceCitation.question_version_id == current.id,
            or_(
                AcademicDocument.visibility != "cohort",
                Subject.resource_sharing_enabled.is_(False),
            ),
        )
        .limit(1)
    )
    return inaccessible_source is None


@router.post(
    "/workspaces/{workspace_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    workspace_id: UUID,
    payload: QuestionCreate,
    db: DatabaseSession,
    membership: ActiveMember,
) -> QuestionResponse:
    subject = db.scalar(
        select(Subject).where(
            Subject.id == payload.subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    if payload.visibility == "cohort" and not _is_staff(membership):
        raise HTTPException(status_code=403, detail="Only authorised staff can create cohort questions.")
    _validate_taxonomy(
        db, workspace_id, payload.subject_id, payload.topic_id, payload.learning_outcome_id
    )
    citations = _load_citation_segments(
        db=db,
        workspace_id=workspace_id,
        subject_id=payload.subject_id,
        segment_ids=payload.content.source_segment_ids,
        membership=membership,
        visibility=payload.visibility,
    )
    question = Question(
        workspace_id=workspace_id,
        subject_id=payload.subject_id,
        created_by=membership.user_id,
        visibility=payload.visibility,
        current_version_number=0,
    )
    db.add(question)
    db.flush()
    _append_question_version(
        db=db,
        question=question,
        topic_id=payload.topic_id,
        learning_outcome_id=payload.learning_outcome_id,
        content=payload.content,
        citations=citations,
        actor_user_id=membership.user_id,
    )
    record_audit_event(
        db,
        action="question_bank.question_created",
        resource_type="question",
        resource_id=str(question.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"subject_id": str(payload.subject_id), "visibility": payload.visibility},
    )
    db.commit()
    return _public_question(_load_question(db, workspace_id, question.id))


@router.get(
    "/workspaces/{workspace_id}/questions",
    response_model=list[QuestionResponse],
)
def list_questions(
    workspace_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
    subject_id: UUID | None = None,
) -> list[QuestionResponse]:
    statement = (
        select(Question)
        .where(Question.workspace_id == workspace_id)
        .options(selectinload(Question.versions).selectinload(QuestionVersion.citations))
        .order_by(Question.updated_at.desc())
    )
    if subject_id is not None:
        statement = statement.where(Question.subject_id == subject_id)
    questions = db.scalars(statement).unique().all()
    visible = [item for item in questions if _can_view_question(db, item, membership)]
    return [_public_question(item) for item in visible]


@router.get(
    "/workspaces/{workspace_id}/questions/{question_id}",
    response_model=QuestionResponse,
)
def get_question(
    workspace_id: UUID,
    question_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> QuestionResponse:
    question = _load_question(db, workspace_id, question_id)
    if not _can_view_question(db, question, membership):
        raise HTTPException(status_code=404, detail="Question not found.")
    return _public_question(question)


@router.get(
    "/workspaces/{workspace_id}/questions/{question_id}/authoring",
    response_model=QuestionAuthoringResponse,
)
def get_question_authoring(
    workspace_id: UUID,
    question_id: UUID,
    db: DatabaseSession,
    _staff: StaffMember,
) -> QuestionAuthoringResponse:
    return _authoring_question(_load_question(db, workspace_id, question_id))


@router.post(
    "/workspaces/{workspace_id}/questions/{question_id}/versions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_question_version(
    workspace_id: UUID,
    question_id: UUID,
    payload: QuestionVersionAppend,
    db: DatabaseSession,
    membership: ActiveMember,
) -> QuestionResponse:
    question = db.scalar(
        select(Question)
        .where(
            Question.id == question_id,
            Question.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if question is None or (question.created_by != membership.user_id and not _is_staff(membership)):
        raise HTTPException(status_code=404, detail="Question not found.")
    if question.visibility == "cohort" and not _is_staff(membership):
        raise HTTPException(status_code=403, detail="Only staff may revise cohort questions.")
    _validate_taxonomy(
        db, workspace_id, question.subject_id, payload.topic_id, payload.learning_outcome_id
    )
    citations = _load_citation_segments(
        db=db,
        workspace_id=workspace_id,
        subject_id=question.subject_id,
        segment_ids=payload.content.source_segment_ids,
        membership=membership,
        visibility=question.visibility,
    )
    _append_question_version(
        db=db,
        question=question,
        topic_id=payload.topic_id,
        learning_outcome_id=payload.learning_outcome_id,
        content=payload.content,
        citations=citations,
        actor_user_id=membership.user_id,
    )
    record_audit_event(
        db,
        action="question_bank.question_version_created",
        resource_type="question",
        resource_id=str(question.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"version_number": question.current_version_number},
    )
    db.commit()
    return _public_question(_load_question(db, workspace_id, question.id))


@router.post(
    "/workspaces/{workspace_id}/questions/{question_id}/versions/{version_id}/approve",
    response_model=QuestionAuthoringResponse,
)
def approve_question_version(
    workspace_id: UUID,
    question_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    membership: StaffMember,
) -> QuestionAuthoringResponse:
    question = _load_question(db, workspace_id, question_id)
    version = next((item for item in question.versions if item.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Question version not found.")
    if version.status != QuestionVersionStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft question versions can be approved.")
    if not version.citations:
        raise HTTPException(status_code=409, detail="A question cannot be approved without source citations.")
    if version.question_type in {"diagram_interpretation", "diagram_construction"}:
        raise HTTPException(
            status_code=409,
            detail="Diagram questions remain blocked until the visual asset review workflow is implemented.",
        )
    version.status = QuestionVersionStatus.APPROVED
    version.approved_by = membership.user_id
    version.approved_at = datetime.now(UTC)
    record_audit_event(
        db,
        action="question_bank.question_version_approved",
        resource_type="question_version",
        resource_id=str(version.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"question_id": str(question.id), "version_number": version.version_number},
    )
    db.commit()
    return _authoring_question(_load_question(db, workspace_id, question.id))


@router.post(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{blueprint_version_id}/generate-questions",
    response_model=QuestionGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_blueprint_questions(
    workspace_id: UUID,
    blueprint_id: UUID,
    blueprint_version_id: UUID,
    payload: QuestionGenerationRequest,
    request: Request,
    db: DatabaseSession,
    membership: ActiveMember,
    generator: QuestionGenerator,
) -> QuestionGenerationResponse:
    blueprint = db.scalar(
        select(ExamBlueprint).where(
            ExamBlueprint.id == blueprint_id,
            ExamBlueprint.workspace_id == workspace_id,
        )
    )
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Examination blueprint not found.")
    blueprint_version = db.scalar(
        select(ExamBlueprintVersion)
        .where(
            ExamBlueprintVersion.id == blueprint_version_id,
            ExamBlueprintVersion.blueprint_id == blueprint_id,
        )
        .options(
            selectinload(ExamBlueprintVersion.topic_weights),
            selectinload(ExamBlueprintVersion.outcome_weights),
        )
    )
    if blueprint_version is None:
        raise HTTPException(status_code=404, detail="Blueprint version not found.")
    if blueprint_version.status != BlueprintVersionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Question generation requires an approved blueprint version.")
    if blueprint_version.question_count > 30:
        raise HTTPException(
            status_code=422,
            detail="Synchronous generation is limited to 30 questions per request; split larger blueprints into batches.",
        )
    enforce_auth_rate_limit(
        request,
        db,
        scope="question_generation",
        subject=str(membership.user_id),
        limit=10,
        window_seconds=3600,
        include_client=False,
    )

    subject = db.scalar(
        select(Subject).where(
            Subject.id == blueprint_version.subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Blueprint subject not found.")

    source_segments: list[dict[str, str]] = []
    segment_map: dict[UUID, tuple[DocumentTextSegment, DocumentVersion]] = {}
    total_characters = 0
    segment_count = 0
    for source_version_id in payload.source_version_ids:
        version = db.scalar(
            select(DocumentVersion)
            .join(AcademicDocument, AcademicDocument.id == DocumentVersion.document_id)
            .join(Subject, Subject.id == AcademicDocument.subject_id)
            .join(DocumentExtraction, DocumentExtraction.version_id == DocumentVersion.id)
            .where(
                DocumentVersion.id == source_version_id,
                AcademicDocument.workspace_id == workspace_id,
                AcademicDocument.subject_id == blueprint_version.subject_id,
                Subject.workspace_id == workspace_id,
                DocumentExtraction.status == ExtractionStatus.EXTRACTED,
            )
        )
        if version is None:
            raise HTTPException(
                status_code=422,
                detail="Every selected source must be extracted material from the blueprint subject.",
            )
        document = db.get(AcademicDocument, version.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Coursework source not found.")
        owner_access = document.created_by == membership.user_id
        cohort_access = document.visibility == "cohort" and subject.resource_sharing_enabled
        if not (owner_access or cohort_access or _is_staff(membership)):
            raise HTTPException(status_code=404, detail="A selected coursework source is not accessible.")
        latest_review = db.scalar(
            select(DocumentExtractionReview)
            .where(DocumentExtractionReview.version_id == version.id)
            .order_by(DocumentExtractionReview.created_at.desc(), DocumentExtractionReview.id.desc())
            .limit(1)
        )
        if latest_review is not None and latest_review.decision == "rejected":
            raise HTTPException(status_code=409, detail="Rejected extraction cannot be used for generation.")
        segments = db.scalars(
            select(DocumentTextSegment)
            .join(DocumentExtraction, DocumentExtraction.id == DocumentTextSegment.extraction_id)
            .where(DocumentExtraction.version_id == version.id)
            .order_by(DocumentTextSegment.ordinal)
        ).all()
        if not segments:
            raise HTTPException(status_code=409, detail="A selected source has no extracted text segments.")
        for segment in segments:
            segment_count += 1
            if segment_count > 200:
                raise HTTPException(status_code=413, detail="Selected sources contain too many extracted segments.")
            total_characters += len(segment.text)
            if total_characters > 100_000:
                raise HTTPException(status_code=413, detail="Selected source material exceeds the generation limit.")
            source_segments.append(
                {
                    "id": str(segment.id),
                    "locator": segment.locator,
                    "text": segment.text[:20_000],
                }
            )
            segment_map[segment.id] = (segment, version)

    if not source_segments:
        raise HTTPException(status_code=422, detail="At least one extracted source segment is required.")

    topic_ids = [item.topic_id for item in blueprint_version.topic_weights]
    topics = db.scalars(select(Topic).where(Topic.id.in_(topic_ids))).all()
    outcome_ids = [item.learning_outcome_id for item in blueprint_version.outcome_weights]
    outcomes = db.scalars(select(LearningOutcome).where(LearningOutcome.id.in_(outcome_ids))).all()
    topic_context = [{"id": str(item.id), "name": item.name} for item in topics]
    outcome_context = [
        {"id": str(item.id), "code": item.code, "description": item.description}
        for item in outcomes
    ]

    try:
        generated = await generator.generate(
            blueprint_version=blueprint_version,
            subject_name=subject.name,
            topic_context=topic_context,
            outcome_context=outcome_context,
            source_segments=source_segments,
        )
    except QuestionGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    created: list[Question] = []
    try:
        for item in generated:
            content = item["content"]
            citations = {
                segment_id: segment_map[segment_id]
                for segment_id in content.source_segment_ids
            }
            question = Question(
                workspace_id=workspace_id,
                subject_id=blueprint_version.subject_id,
                created_by=membership.user_id,
                visibility="private",
                current_version_number=0,
            )
            db.add(question)
            db.flush()
            _append_question_version(
                db=db,
                question=question,
                topic_id=item["topic_id"],
                learning_outcome_id=item["learning_outcome_id"],
                content=content,
                citations=citations,
                actor_user_id=membership.user_id,
                generation_method="ai",
                generation_model=get_settings().openai_model,
            )
            created.append(question)
        record_audit_event(
            db,
            action="question_bank.blueprint_questions_generated",
            resource_type="exam_blueprint_version",
            resource_id=str(blueprint_version.id),
            actor_user_id=membership.user_id,
            workspace_id=workspace_id,
            event_data={
                "blueprint_id": str(blueprint_id),
                "generated_count": len(created),
                "source_version_ids": [str(item) for item in payload.source_version_ids],
            },
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise

    results = [_public_question(_load_question(db, workspace_id, item.id)) for item in created]
    return QuestionGenerationResponse(
        blueprint_version_id=blueprint_version.id,
        generated_count=len(results),
        total_marks=sum(
            version.marks for question in results for version in question.versions
            if version.version_number == question.current_version_number
        ),
        questions=results,
    )
