"""Subject workspace endpoints — creation, isolation, uploads, classification."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (
    AcademicDocument,
    ExtractedContent,
    LearningOutcome,
    ResourceSufficiencyReport,
    SubjectWorkspace,
    Subtopic,
    Topic,
    User,
    VisualAsset,
)
from ...schemas import (
    DocumentOut,
    ExtractedContentOut,
    SufficiencyOut,
    TopicOut,
    TopicUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from ...security import get_current_user, require_workspace
from ...services import extraction as extraction_service
from ...services import workspace as ws

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> list[SubjectWorkspace]:
    return list(db.scalars(select(SubjectWorkspace).where(
        SubjectWorkspace.owner_id == user.id).order_by(SubjectWorkspace.created_at.desc())))


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> SubjectWorkspace:
    duplicate = db.scalars(select(SubjectWorkspace).where(
        SubjectWorkspace.owner_id == user.id,
        SubjectWorkspace.name == payload.name)).first()
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A subject workspace with this name already exists")
    workspace = SubjectWorkspace(
        owner_id=user.id,
        name=payload.name,
        code=payload.code,
        module=payload.module,
        institution=payload.institution,
        qualification=payload.qualification,
        description=payload.description,
    )
    db.add(workspace)
    db.flush()
    ws.audit(db, workspace.id, user.id, "workspace.created", "workspace", workspace.id,
             {"name": workspace.name})
    db.commit()
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(workspace: SubjectWorkspace = Depends(require_workspace)) -> SubjectWorkspace:
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(payload: WorkspaceUpdate,
                     workspace: SubjectWorkspace = Depends(require_workspace),
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> SubjectWorkspace:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    db.flush()
    ws.audit(db, workspace.id, user.id, "workspace.updated", "workspace", workspace.id,
             payload.model_dump(exclude_unset=True))
    db.commit()
    return workspace


@router.get("/{workspace_id}/summary")
def workspace_summary(workspace: SubjectWorkspace = Depends(require_workspace),
                      db: Session = Depends(get_db)) -> dict:
    return ws.workspace_summary(db, workspace)


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------

@router.post("/{workspace_id}/documents", response_model=DocumentOut,
             status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace: SubjectWorkspace = Depends(require_workspace),
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AcademicDocument:
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if not extraction_service.is_supported(file.filename or ""):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type. Supported: "
            f"{', '.join(sorted(extraction_service.SUPPORTED_EXTENSIONS))}")
    try:
        document = ws.store_upload(db, workspace, file.filename or "upload",
                                   content, file.content_type or "")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    ws.process_document(db, document)
    db.commit()
    db.refresh(document)
    return document


@router.get("/{workspace_id}/documents", response_model=list[DocumentOut])
def list_documents(workspace: SubjectWorkspace = Depends(require_workspace),
                   db: Session = Depends(get_db),
                   include_history: bool = False) -> list[AcademicDocument]:
    query = select(AcademicDocument).where(AcademicDocument.workspace_id == workspace.id)
    if not include_history:
        query = query.where(AcademicDocument.is_latest.is_(True))
    return list(db.scalars(query.order_by(AcademicDocument.created_at.desc())))


@router.get("/{workspace_id}/documents/{document_id}/content",
            response_model=list[ExtractedContentOut])
def document_content(document_id: str,
                     workspace: SubjectWorkspace = Depends(require_workspace),
                     db: Session = Depends(get_db)) -> list[ExtractedContent]:
    document = db.get(AcademicDocument, document_id)
    if document is None or document.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    return list(db.scalars(select(ExtractedContent).where(
        ExtractedContent.document_id == document_id).order_by(ExtractedContent.ordinal)))


@router.post("/{workspace_id}/documents/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(document_id: str,
                       workspace: SubjectWorkspace = Depends(require_workspace),
                       db: Session = Depends(get_db)) -> AcademicDocument:
    document = db.get(AcademicDocument, document_id)
    if document is None or document.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    for chunk in list(db.scalars(select(ExtractedContent).where(
            ExtractedContent.document_id == document_id))):
        db.delete(chunk)
    db.flush()
    ws.process_document(db, document)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/{workspace_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str,
                    workspace: SubjectWorkspace = Depends(require_workspace),
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> None:
    document = db.get(AcademicDocument, document_id)
    if document is None or document.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    ws.audit(db, workspace.id, user.id, "document.deleted", "document", document_id,
             {"filename": document.filename})
    db.delete(document)
    db.commit()


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

@router.post("/{workspace_id}/classify", response_model=SufficiencyOut)
def classify_workspace(workspace: SubjectWorkspace = Depends(require_workspace),
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> ResourceSufficiencyReport:
    report = ws.reclassify(db, workspace)
    db.commit()
    db.refresh(report)
    return report


@router.get("/{workspace_id}/sufficiency", response_model=SufficiencyOut)
def latest_sufficiency(workspace: SubjectWorkspace = Depends(require_workspace),
                       db: Session = Depends(get_db)) -> ResourceSufficiencyReport:
    report = db.scalars(select(ResourceSufficiencyReport).where(
        ResourceSufficiencyReport.workspace_id == workspace.id
    ).order_by(ResourceSufficiencyReport.created_at.desc())).first()
    if report is None:
        report = ws.reclassify(db, workspace)
        db.commit()
        db.refresh(report)
    return report


@router.get("/{workspace_id}/topics", response_model=list[TopicOut])
def list_topics(workspace: SubjectWorkspace = Depends(require_workspace),
                db: Session = Depends(get_db)) -> list[dict]:
    topics = list(db.scalars(select(Topic).where(
        Topic.workspace_id == workspace.id).order_by(Topic.confidence.desc())))
    out: list[dict] = []
    for topic in topics:
        subtopics = list(db.scalars(select(Subtopic).where(Subtopic.topic_id == topic.id)))
        outcomes = list(db.scalars(select(LearningOutcome).where(
            LearningOutcome.topic_id == topic.id)))
        out.append({
            "id": topic.id, "name": topic.name, "summary": topic.summary,
            "coverage": topic.coverage, "coverage_notes": topic.coverage_notes,
            "needs_visual": topic.needs_visual, "visual_rationale": topic.visual_rationale,
            "confidence": topic.confidence,
            "reviewed_by_student": topic.reviewed_by_student,
            "subtopics": [
                {"id": s.id, "name": s.name, "summary": s.summary, "coverage": s.coverage,
                 "outcomes": [{"id": o.id, "statement": o.statement, "bloom": o.bloom,
                               "covered": o.covered, "subtopic_id": o.subtopic_id}
                              for o in outcomes if o.subtopic_id == s.id]}
                for s in subtopics],
        })
    return out


@router.patch("/{workspace_id}/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: str, payload: TopicUpdate,
                 workspace: SubjectWorkspace = Depends(require_workspace),
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found in this workspace")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(topic, field, value)
    topic.reviewed_by_student = True
    db.flush()
    ws.audit(db, workspace.id, user.id, "topic.updated", "topic", topic.id,
             payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(topic)
    subtopics = list(db.scalars(select(Subtopic).where(Subtopic.topic_id == topic.id)))
    outcomes = list(db.scalars(select(LearningOutcome).where(
        LearningOutcome.topic_id == topic.id)))
    return {
        "id": topic.id, "name": topic.name, "summary": topic.summary,
        "coverage": topic.coverage, "coverage_notes": topic.coverage_notes,
        "needs_visual": topic.needs_visual, "visual_rationale": topic.visual_rationale,
        "confidence": topic.confidence, "reviewed_by_student": topic.reviewed_by_student,
        "subtopics": [
            {"id": s.id, "name": s.name, "summary": s.summary, "coverage": s.coverage,
             "outcomes": [{"id": o.id, "statement": o.statement, "bloom": o.bloom,
                           "covered": o.covered, "subtopic_id": o.subtopic_id}
                          for o in outcomes if o.subtopic_id == s.id]}
            for s in subtopics],
    }


# --------------------------------------------------------------------------
# Visuals
# --------------------------------------------------------------------------

@router.post("/{workspace_id}/visuals/propose")
def propose_visuals(workspace: SubjectWorkspace = Depends(require_workspace),
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    created = ws.propose_visuals(db, workspace)
    db.commit()
    return {"created": len(created), "visual_ids": [v.id for v in created]}


@router.get("/{workspace_id}/visuals")
def list_visuals(workspace: SubjectWorkspace = Depends(require_workspace),
                 db: Session = Depends(get_db)) -> list[dict]:
    assets = list(db.scalars(select(VisualAsset).where(
        VisualAsset.workspace_id == workspace.id).order_by(VisualAsset.created_at)))
    return [
        {"id": a.id, "key": a.key, "title": a.title, "diagram_type": a.diagram_type,
         "requirement": a.requirement, "status": a.status, "version": a.version,
         "labels": a.labels, "intended_use": a.intended_use, "topic_id": a.topic_id,
         "svg": a.svg, "approved_at": a.approved_at.isoformat() if a.approved_at else None}
        for a in assets
    ]


@router.post("/{workspace_id}/visuals/{visual_id}/decision")
def decide_visual(visual_id: str, payload: dict,
                  workspace: SubjectWorkspace = Depends(require_workspace),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    asset = db.get(VisualAsset, visual_id)
    if asset is None or asset.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visual not found in this workspace")
    decision = str(payload.get("decision", "")).lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be approve or reject")
    ws.approve_visual(db, asset, decision == "approve", user.id)
    db.commit()
    return {"id": asset.id, "status": asset.status, "version": asset.version}


@router.post("/{workspace_id}/visuals/{visual_id}/revise")
def revise_visual(visual_id: str, payload: dict,
                  workspace: SubjectWorkspace = Depends(require_workspace),
                  db: Session = Depends(get_db)) -> dict:
    asset = db.get(VisualAsset, visual_id)
    if asset is None or asset.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visual not found in this workspace")
    labels = payload.get("labels")
    if labels is not None and not isinstance(labels, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "labels must be a list of strings")
    ws.revise_visual(db, asset, title=payload.get("title"), labels=labels)
    db.commit()
    return {"id": asset.id, "version": asset.version, "status": asset.status,
            "svg": asset.svg, "labels": asset.labels}
