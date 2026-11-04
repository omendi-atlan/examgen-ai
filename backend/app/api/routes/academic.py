"""Workspace-scoped academic source ingestion and classification routes."""

import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_workspace_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AcademicDocument,
    ClassificationMethod,
    DocumentExtraction,
    DocumentTextSegment,
    DocumentTopicClassification,
    DocumentVersion,
    ExtractionStatus,
    MembershipRole,
    Subject,
    Topic,
    WorkspaceMembership,
)
from app.schemas.academic import (
    ClassificationRequest,
    ClassificationResponse,
    DocumentResponse,
    DocumentVersionResponse,
    ExtractionResponse,
    SubjectCreate,
    SubjectResponse,
    TextSegmentResponse,
    TopicCreate,
    TopicResponse,
)
from app.services.audit import record_audit_event
from app.services.document_extraction import extract_document
from app.services.document_storage import resolve_storage_path, store_upload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["academic-ingestion"])
DatabaseSession = Annotated[Session, Depends(get_db)]
WorkspaceEditor = Annotated[
    WorkspaceMembership,
    Depends(
        require_workspace_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.EXAMINER,
        )
    ),
]


def _version_response(version: DocumentVersion) -> DocumentVersionResponse:
    extraction = version.extraction
    classifications = [
        ClassificationResponse(
            id=item.id,
            topic_id=item.topic_id,
            subject_id=item.topic.subject_id,
            subject_name=item.topic.subject.name,
            topic_name=item.topic.name,
            method=item.method.value,
            rationale=item.rationale,
            classified_by=item.classified_by,
            created_at=item.created_at,
        )
        for item in version.classifications
    ]
    extraction_response = None
    if extraction is not None:
        extraction_response = ExtractionResponse(
            id=extraction.id,
            status=extraction.status.value,
            parser_name=extraction.parser_name,
            parser_version=extraction.parser_version,
            page_count=extraction.page_count,
            character_count=extraction.character_count,
            segment_count=len(extraction.segments),
            error_message=extraction.error_message,
        )
    return DocumentVersionResponse(
        id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        media_type=version.media_type,
        size_bytes=version.size_bytes,
        sha256=version.sha256,
        source_type=version.source_type,
        source_reference=version.source_reference,
        publisher=version.publisher,
        published_on=version.published_on,
        provenance=version.provenance,
        uploaded_by=version.uploaded_by,
        created_at=version.created_at,
        extraction=extraction_response,
        classifications=classifications,
    )


def _document_response(document: AcademicDocument) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        current_version_number=document.current_version_number,
        created_by=document.created_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
        versions=[_version_response(version) for version in document.versions],
    )


def _load_document(db: Session, workspace_id: UUID, document_id: UUID) -> AcademicDocument:
    statement = (
        select(AcademicDocument)
        .where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
        )
        .options(
            selectinload(AcademicDocument.versions)
            .selectinload(DocumentVersion.extraction)
            .selectinload(DocumentExtraction.segments),
            selectinload(AcademicDocument.versions)
            .selectinload(DocumentVersion.classifications)
            .selectinload(DocumentTopicClassification.topic)
            .selectinload(Topic.subject),
        )
    )
    document = db.scalar(statement)
    if document is None:
        raise HTTPException(status_code=404, detail="Academic document not found.")
    return document


async def _ingest_version(
    *,
    db: Session,
    workspace_id: UUID,
    document: AcademicDocument,
    upload: UploadFile,
    uploaded_by: UUID,
    source_type: str | None,
    source_reference: str | None,
    publisher: str | None,
    published_on: object | None,
) -> DocumentVersion:
    settings = get_settings()
    stored = await store_upload(
        upload,
        Path(settings.document_storage_path),
        settings.max_document_upload_bytes,
    )
    storage_path = resolve_storage_path(Path(settings.document_storage_path), stored.storage_key)
    existing = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.sha256 == stored.sha256,
        )
    )
    if existing is not None:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="This exact file version already exists.")

    version_number = document.current_version_number + 1 if document.id else 1
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        media_type=stored.media_type,
        file_extension=stored.extension,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        source_type=source_type.strip() if source_type else None,
        source_reference=source_reference.strip() if source_reference else None,
        publisher=publisher.strip() if publisher else None,
        published_on=published_on,
        provenance={
            "ingestion_channel": "authenticated_workspace_upload",
            "original_filename": stored.original_filename,
            "sha256": stored.sha256,
        },
        uploaded_by=uploaded_by,
    )
    try:
        db.add(version)
        db.flush()
        try:
            result = extract_document(storage_path, stored.extension)
            extraction = DocumentExtraction(
                version_id=version.id,
                status=(
                    ExtractionStatus.NEEDS_OCR
                    if result.needs_ocr
                    else ExtractionStatus.EXTRACTED
                    if result.segments
                    else ExtractionStatus.EMPTY
                ),
                parser_name=result.parser_name,
                parser_version=result.parser_version,
                page_count=result.page_count,
                character_count=sum(len(segment.text) for segment in result.segments),
                extraction_metadata=result.metadata,
            )
            db.add(extraction)
            db.flush()
            db.add_all(
                [
                    DocumentTextSegment(
                        extraction_id=extraction.id,
                        ordinal=index,
                        locator=segment.locator,
                        text=segment.text,
                        metadata_json=segment.metadata,
                    )
                    for index, segment in enumerate(result.segments, start=1)
                ]
            )
        except Exception as exc:
            logger.exception("Academic document extraction failed for version %s", version.id)
            db.add(
                DocumentExtraction(
                    version_id=version.id,
                    status=ExtractionStatus.FAILED,
                    parser_name="unavailable",
                    parser_version="0",
                    character_count=0,
                    extraction_metadata={},
                    error_message=f"Extraction failed ({type(exc).__name__}).",
                )
            )
        document.current_version_number = version_number
        record_audit_event(
            db,
            action="academic_document.version_uploaded",
            resource_type="academic_document_version",
            resource_id=str(version.id),
            actor_user_id=uploaded_by,
            workspace_id=workspace_id,
            event_data={
                "document_id": str(document.id),
                "version_number": version_number,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            },
        )
        db.commit()
        db.refresh(version)
        return version
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_academic_document(
    workspace_id: UUID,
    db: DatabaseSession,
    membership: WorkspaceEditor,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=240)],
    source_type: Annotated[str | None, Form(max_length=80)] = None,
    source_reference: Annotated[str | None, Form(max_length=1000)] = None,
    publisher: Annotated[str | None, Form(max_length=240)] = None,
    published_on: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """Create a logical document, immutable version one and its extraction record."""
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Document title cannot be blank.")
    document = AcademicDocument(
        workspace_id=workspace_id,
        title=clean_title,
        created_by=membership.user_id,
        current_version_number=0,
    )
    db.add(document)
    db.flush()
    try:
        version = await _ingest_version(
            db=db,
            workspace_id=workspace_id,
            document=document,
            upload=file,
            uploaded_by=membership.user_id,
            source_type=source_type,
            source_reference=source_reference,
            publisher=publisher,
            published_on=published_on,
        )
        document.current_version_number = version.version_number
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _document_response(_load_document(db, workspace_id, document.id))


@router.post(
    "/workspaces/{workspace_id}/documents/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_version(
    workspace_id: UUID,
    document_id: UUID,
    db: DatabaseSession,
    membership: WorkspaceEditor,
    file: Annotated[UploadFile, File()],
    source_type: Annotated[str | None, Form(max_length=80)] = None,
    source_reference: Annotated[str | None, Form(max_length=1000)] = None,
    publisher: Annotated[str | None, Form(max_length=240)] = None,
    published_on: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """Append a new immutable version; earlier source versions remain unchanged."""
    document = db.scalar(
        select(AcademicDocument)
        .where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Academic document not found.")
    await _ingest_version(
        db=db,
        workspace_id=workspace_id,
        document=document,
        upload=file,
        uploaded_by=membership.user_id,
        source_type=source_type,
        source_reference=source_reference,
        publisher=publisher,
        published_on=published_on,
    )
    return _document_response(_load_document(db, workspace_id, document.id))


@router.get(
    "/workspaces/{workspace_id}/documents",
    response_model=list[DocumentResponse],
)
def list_academic_documents(
    workspace_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> list[DocumentResponse]:
    """List workspace documents and their version/extraction provenance."""
    ids = db.scalars(
        select(AcademicDocument.id)
        .where(AcademicDocument.workspace_id == workspace_id)
        .order_by(AcademicDocument.updated_at.desc())
    ).all()
    return [
        _document_response(_load_document(db, workspace_id, document_id))
        for document_id in ids
    ]


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_academic_document(
    workspace_id: UUID,
    document_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> DocumentResponse:
    """Retrieve document metadata, immutable versions and provenance."""
    return _document_response(_load_document(db, workspace_id, document_id))


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/segments",
    response_model=list[TextSegmentResponse],
)
def get_document_segments(
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> list[TextSegmentResponse]:
    """Read extracted source segments with page/slide/paragraph locators."""
    document = db.scalar(
        select(AcademicDocument).where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Academic document not found.")
    version = db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
        .options(selectinload(DocumentVersion.extraction).selectinload(DocumentExtraction.segments))
    )
    if version is None or version.extraction is None:
        raise HTTPException(status_code=404, detail="Document extraction not found.")
    return [
        TextSegmentResponse(
            id=segment.id,
            ordinal=segment.ordinal,
            locator=segment.locator,
            text=segment.text,
            metadata=segment.metadata_json,
        )
        for segment in version.extraction.segments
    ]


@router.post(
    "/workspaces/{workspace_id}/taxonomy/subjects",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_subject(
    workspace_id: UUID,
    payload: SubjectCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> Subject:
    """Create a workspace-owned subject; no inferred subjects are created."""
    subject = Subject(
        workspace_id=workspace_id,
        name=payload.name,
        normalized_name=payload.name.casefold(),
        description=payload.description,
        created_by=membership.user_id,
    )
    db.add(subject)
    try:
        db.commit()
        db.refresh(subject)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Subject already exists in this workspace.") from None
    record_audit_event(
        db,
        action="taxonomy.subject_created",
        resource_type="subject",
        resource_id=str(subject.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
    )
    db.commit()
    return subject


@router.get(
    "/workspaces/{workspace_id}/taxonomy/subjects",
    response_model=list[SubjectResponse],
)
def list_subjects(
    workspace_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> list[Subject]:
    return list(
        db.scalars(
            select(Subject)
            .where(Subject.workspace_id == workspace_id)
            .order_by(Subject.normalized_name)
        ).all()
    )


@router.post(
    "/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics",
    response_model=TopicResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    workspace_id: UUID,
    subject_id: UUID,
    payload: TopicCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> Topic:
    """Create a topic under a subject in the same workspace."""
    subject = db.scalar(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    topic = Topic(
        workspace_id=workspace_id,
        subject_id=subject_id,
        name=payload.name,
        normalized_name=payload.name.casefold(),
        description=payload.description,
        created_by=membership.user_id,
    )
    db.add(topic)
    try:
        db.commit()
        db.refresh(topic)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Topic already exists under this subject.") from None
    record_audit_event(
        db,
        action="taxonomy.topic_created",
        resource_type="topic",
        resource_id=str(topic.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
    )
    db.commit()
    return topic


@router.get(
    "/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics",
    response_model=list[TopicResponse],
)
def list_topics(
    workspace_id: UUID,
    subject_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> list[Topic]:
    subject = db.scalar(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    return list(
        db.scalars(
            select(Topic)
            .where(Topic.workspace_id == workspace_id, Topic.subject_id == subject_id)
            .order_by(Topic.normalized_name)
        ).all()
    )


@router.put(
    "/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/classifications",
    response_model=list[ClassificationResponse],
)
def classify_document_version(
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    payload: ClassificationRequest,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> list[ClassificationResponse]:
    """Replace a version's topic assignments with explicit human-confirmed taxonomy."""
    document = db.scalar(
        select(AcademicDocument).where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Academic document not found.")
    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Document version not found.")
    topic_ids = set(payload.topic_ids)
    if len(topic_ids) != len(payload.topic_ids):
        raise HTTPException(status_code=422, detail="Duplicate topic identifiers are not allowed.")
    topics = list(
        db.scalars(
            select(Topic)
            .where(Topic.workspace_id == workspace_id, Topic.id.in_(topic_ids))
            .options(selectinload(Topic.subject))
        ).all()
    )
    if len(topics) != len(topic_ids):
        raise HTTPException(status_code=422, detail="Every topic must belong to this workspace.")
    db.query(DocumentTopicClassification).filter(
        DocumentTopicClassification.version_id == version_id
    ).delete(synchronize_session=False)
    assignments = [
        DocumentTopicClassification(
            version_id=version_id,
            topic_id=topic.id,
            method=ClassificationMethod.HUMAN,
            rationale=payload.rationale,
            classified_by=membership.user_id,
        )
        for topic in topics
    ]
    db.add_all(assignments)
    record_audit_event(
        db,
        action="academic_document.classified",
        resource_type="academic_document_version",
        resource_id=str(version_id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"topic_ids": [str(topic.id) for topic in topics], "method": "human"},
    )
    db.commit()
    return [
        ClassificationResponse(
            id=assignment.id,
            topic_id=topic.id,
            subject_id=topic.subject_id,
            subject_name=topic.subject.name,
            topic_name=topic.name,
            method=ClassificationMethod.HUMAN.value,
            rationale=payload.rationale,
            classified_by=membership.user_id,
            created_at=assignment.created_at,
        )
        for assignment, topic in zip(assignments, topics, strict=True)
    ]
