"""Student-facing academic resources embedded in subject coursework.

This router deliberately reuses the canonical AcademicDocument, DocumentVersion,
extraction queue, storage, provenance and audit services. It does not create a
second document store or expose examiner governance operations to students.
"""
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_workspace_membership,
    limit_document_upload_attempts,
    require_workspace_roles,
)
from app.api.routes.academic import _document_response, _ingest_version, _load_document
from app.core.database import get_db
from app.models import (
    AcademicDocument,
    DocumentExtraction,
    DocumentTextSegment,
    DocumentVersion,
    MembershipRole,
    Subject,
    WorkspaceMembership,
)
from app.schemas.academic import DocumentResponse, TextSegmentResponse
from app.services.audit import record_audit_event

router = APIRouter(tags=["student-coursework-resources"])
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


class ResourceSharingPolicyRequest(BaseModel):
    enabled: bool


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


def _visible_document(
    db: Session,
    workspace_id: UUID,
    subject_id: UUID,
    document_id: UUID,
    user_id: UUID,
) -> AcademicDocument:
    statement = (
        select(AcademicDocument)
        .join(Subject, Subject.id == AcademicDocument.subject_id)
        .where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
            AcademicDocument.subject_id == subject_id,
            or_(
                AcademicDocument.created_by == user_id,
                and_(
                    AcademicDocument.visibility == "cohort",
                    Subject.resource_sharing_enabled.is_(True),
                ),
            ),
        )
    )
    document = db.scalar(statement)
    if document is None:
        # Do not disclose whether another student's private resource exists.
        raise HTTPException(status_code=404, detail="Coursework resource not found.")
    return document


@router.put(
    "/workspaces/{workspace_id}/subjects/{subject_id}/resource-sharing",
)
def update_resource_sharing_policy(
    workspace_id: UUID,
    subject_id: UUID,
    payload: ResourceSharingPolicyRequest,
    db: DatabaseSession,
    _staff: StaffMember,
) -> dict[str, object]:
    """Enable/disable cohort sharing under staff control; private remains the default."""
    subject = _subject(db, workspace_id, subject_id)
    subject.resource_sharing_enabled = payload.enabled
    record_audit_event(
        db,
        action="coursework.resource_sharing_policy_updated",
        resource_type="subject",
        resource_id=str(subject.id),
        actor_user_id=_staff.user_id,
        workspace_id=workspace_id,
        event_data={"resource_sharing_enabled": payload.enabled},
    )
    db.commit()
    return {"subject_id": str(subject.id), "resource_sharing_enabled": subject.resource_sharing_enabled}


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/resources",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_document_upload_attempts)],
)
async def upload_coursework_resource(
    workspace_id: UUID,
    subject_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=240)],
    visibility: Annotated[str, Form()] = "private",
    source_type: Annotated[str | None, Form(max_length=80)] = None,
    source_reference: Annotated[str | None, Form(max_length=1000)] = None,
    publisher: Annotated[str | None, Form(max_length=240)] = None,
    published_on: Annotated[date | None, Form()] = None,
) -> DocumentResponse:
    """Upload a resource from its subject page; extraction remains asynchronous."""
    subject = _subject(db, workspace_id, subject_id)
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Resource title cannot be blank.")
    if visibility not in {"private", "cohort"}:
        raise HTTPException(status_code=422, detail="Visibility must be private or cohort.")
    if visibility == "cohort" and not subject.resource_sharing_enabled:
        raise HTTPException(status_code=409, detail="Cohort sharing is not enabled for this subject.")
    document = AcademicDocument(
        workspace_id=workspace_id,
        subject_id=subject_id,
        visibility=visibility,
        title=clean_title,
        created_by=membership.user_id,
        current_version_number=0,
    )
    db.add(document)
    db.flush()
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
    "/workspaces/{workspace_id}/subjects/{subject_id}/resources",
    response_model=list[DocumentResponse],
)
def list_coursework_resources(
    workspace_id: UUID,
    subject_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> list[DocumentResponse]:
    """List the student's private resources and explicitly shared cohort resources."""
    _subject(db, workspace_id, subject_id)
    ids = db.scalars(
        select(AcademicDocument.id)
        .join(Subject, Subject.id == AcademicDocument.subject_id)
        .where(
            AcademicDocument.workspace_id == workspace_id,
            AcademicDocument.subject_id == subject_id,
            or_(
                AcademicDocument.created_by == membership.user_id,
                and_(
                    AcademicDocument.visibility == "cohort",
                    Subject.resource_sharing_enabled.is_(True),
                ),
            ),
        )
        .order_by(AcademicDocument.updated_at.desc())
    ).all()
    return [_document_response(_load_document(db, workspace_id, item_id)) for item_id in ids]


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/resources/{document_id}",
    response_model=DocumentResponse,
)
def get_coursework_resource(
    workspace_id: UUID,
    subject_id: UUID,
    document_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> DocumentResponse:
    _visible_document(db, workspace_id, subject_id, document_id, membership.user_id)
    return _document_response(_load_document(db, workspace_id, document_id))


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/resources/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_document_upload_attempts)],
)
async def append_coursework_resource_version(
    workspace_id: UUID,
    subject_id: UUID,
    document_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
    file: Annotated[UploadFile, File()],
    source_type: Annotated[str | None, Form(max_length=80)] = None,
    source_reference: Annotated[str | None, Form(max_length=1000)] = None,
    publisher: Annotated[str | None, Form(max_length=240)] = None,
    published_on: Annotated[date | None, Form()] = None,
) -> DocumentResponse:
    """Only the original uploader may append a version to a coursework resource."""
    document = db.scalar(
        select(AcademicDocument)
        .where(
            AcademicDocument.id == document_id,
            AcademicDocument.workspace_id == workspace_id,
            AcademicDocument.subject_id == subject_id,
            AcademicDocument.created_by == membership.user_id,
        )
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Coursework resource not found.")
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
    "/workspaces/{workspace_id}/subjects/{subject_id}/resources/{document_id}/versions/{version_id}/segments",
    response_model=list[TextSegmentResponse],
)
def get_coursework_resource_segments(
    workspace_id: UUID,
    subject_id: UUID,
    document_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    membership: ActiveMember,
) -> list[TextSegmentResponse]:
    _visible_document(db, workspace_id, subject_id, document_id, membership.user_id)
    segments = db.scalars(
        select(DocumentTextSegment)
        .join(DocumentExtraction, DocumentTextSegment.extraction_id == DocumentExtraction.id)
        .join(DocumentVersion, DocumentVersion.id == DocumentExtraction.version_id)
        .where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
        .order_by(DocumentTextSegment.ordinal)
    ).all()
    if not segments:
        # Distinguish a valid extraction with no text from a foreign version only by
        # verifying the version belongs to this document; never reveal other objects.
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Coursework resource version not found.")
    return [
        TextSegmentResponse(
            id=item.id,
            ordinal=item.ordinal,
            locator=item.locator,
            text=item.text,
            metadata=item.metadata_json,
        )
        for item in segments
    ]
