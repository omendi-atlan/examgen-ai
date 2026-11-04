"""Workspace-scoped authoring and approval of immutable examination blueprints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_workspace_roles
from app.core.database import get_db
from app.models import (
    BlueprintTopicWeight,
    BlueprintVersionStatus,
    ExamBlueprint,
    ExamBlueprintVersion,
    MembershipRole,
    Subject,
    Topic,
    WorkspaceMembership,
)
from app.schemas.assessment import (
    BlueprintVersionCreate,
    ExamBlueprintResponse,
)
from app.services.audit import record_audit_event

router = APIRouter(tags=["examination-blueprints"])
DatabaseSession = Annotated[Session, Depends(get_db)]
WorkspaceEditor = Annotated[
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
WorkspaceApprover = Annotated[
    WorkspaceMembership,
    Depends(
        require_workspace_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.MODERATOR,
        )
    ),
]


def _validate_taxonomy_scope(
    db: Session,
    workspace_id: UUID,
    payload: BlueprintVersionCreate,
) -> None:
    subject = db.scalar(
        select(Subject).where(
            Subject.id == payload.subject_id,
            Subject.workspace_id == workspace_id,
        )
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found in this workspace.")

    topic_ids = [item.topic_id for item in payload.topic_weights]
    topics = list(
        db.scalars(
            select(Topic).where(
                Topic.id.in_(topic_ids),
                Topic.workspace_id == workspace_id,
                Topic.subject_id == payload.subject_id,
            )
        ).all()
    )
    if len(topics) != len(topic_ids):
        raise HTTPException(
            status_code=422,
            detail="Every blueprint topic must belong to the selected subject and workspace.",
        )


def _load_blueprint(
    db: Session, workspace_id: UUID, blueprint_id: UUID
) -> ExamBlueprint:
    blueprint = db.scalar(
        select(ExamBlueprint)
        .where(
            ExamBlueprint.id == blueprint_id,
            ExamBlueprint.workspace_id == workspace_id,
        )
        .options(
            selectinload(ExamBlueprint.versions).selectinload(
                ExamBlueprintVersion.topic_weights
            )
        )
    )
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Examination blueprint not found.")
    return blueprint


def _append_version(
    *,
    db: Session,
    workspace_id: UUID,
    blueprint: ExamBlueprint,
    payload: BlueprintVersionCreate,
    actor_user_id: UUID,
) -> ExamBlueprintVersion:
    _validate_taxonomy_scope(db, workspace_id, payload)
    version_number = blueprint.current_version_number + 1
    version = ExamBlueprintVersion(
        blueprint_id=blueprint.id,
        version_number=version_number,
        subject_id=payload.subject_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks,
        question_count=payload.question_count,
        cognitive_distribution=payload.cognitive_distribution,
        difficulty_distribution=payload.difficulty_distribution,
        question_type_distribution=payload.question_type_distribution,
        status=BlueprintVersionStatus.DRAFT,
        created_by=actor_user_id,
    )
    db.add(version)
    db.flush()
    db.add_all(
        [
            BlueprintTopicWeight(
                version_id=version.id,
                topic_id=weight.topic_id,
                target_marks=weight.target_marks,
            )
            for weight in payload.topic_weights
        ]
    )
    blueprint.current_version_number = version_number
    record_audit_event(
        db,
        action="exam_blueprint.version_created",
        resource_type="exam_blueprint_version",
        resource_id=str(version.id),
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        event_data={
            "blueprint_id": str(blueprint.id),
            "version_number": version_number,
            "subject_id": str(payload.subject_id),
            "total_marks": payload.total_marks,
            "question_count": payload.question_count,
        },
    )
    return version


@router.post(
    "/workspaces/{workspace_id}/blueprints",
    response_model=ExamBlueprintResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_exam_blueprint(
    workspace_id: UUID,
    payload: BlueprintVersionCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> ExamBlueprint:
    """Create a blueprint identity and its first immutable draft version."""
    blueprint = ExamBlueprint(
        workspace_id=workspace_id,
        created_by=membership.user_id,
        current_version_number=0,
    )
    db.add(blueprint)
    db.flush()
    try:
        _append_version(
            db=db,
            workspace_id=workspace_id,
            blueprint=blueprint,
            payload=payload,
            actor_user_id=membership.user_id,
        )
        record_audit_event(
            db,
            action="exam_blueprint.created",
            resource_type="exam_blueprint",
            resource_id=str(blueprint.id),
            actor_user_id=membership.user_id,
            workspace_id=workspace_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _load_blueprint(db, workspace_id, blueprint.id)


@router.post(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions",
    response_model=ExamBlueprintResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_exam_blueprint_version(
    workspace_id: UUID,
    blueprint_id: UUID,
    payload: BlueprintVersionCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> ExamBlueprint:
    """Append a new draft snapshot; existing blueprint versions are never edited."""
    blueprint = db.scalar(
        select(ExamBlueprint)
        .where(
            ExamBlueprint.id == blueprint_id,
            ExamBlueprint.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Examination blueprint not found.")
    _append_version(
        db=db,
        workspace_id=workspace_id,
        blueprint=blueprint,
        payload=payload,
        actor_user_id=membership.user_id,
    )
    db.commit()
    return _load_blueprint(db, workspace_id, blueprint.id)


@router.get(
    "/workspaces/{workspace_id}/blueprints",
    response_model=list[ExamBlueprintResponse],
)
def list_exam_blueprints(
    workspace_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> list[ExamBlueprint]:
    blueprint_ids = db.scalars(
        select(ExamBlueprint.id)
        .where(ExamBlueprint.workspace_id == workspace_id)
        .order_by(ExamBlueprint.updated_at.desc())
    ).all()
    return [_load_blueprint(db, workspace_id, item_id) for item_id in blueprint_ids]


@router.get(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}",
    response_model=ExamBlueprintResponse,
)
def get_exam_blueprint(
    workspace_id: UUID,
    blueprint_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> ExamBlueprint:
    return _load_blueprint(db, workspace_id, blueprint_id)


@router.post(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/approve",
    response_model=ExamBlueprintResponse,
)
def approve_exam_blueprint_version(
    workspace_id: UUID,
    blueprint_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    membership: WorkspaceApprover,
) -> ExamBlueprint:
    """Record explicit moderator approval without mutating blueprint design content."""
    version = db.scalar(
        select(ExamBlueprintVersion)
        .join(ExamBlueprint, ExamBlueprint.id == ExamBlueprintVersion.blueprint_id)
        .where(
            ExamBlueprint.id == blueprint_id,
            ExamBlueprint.workspace_id == workspace_id,
            ExamBlueprintVersion.id == version_id,
        )
        .options(selectinload(ExamBlueprintVersion.topic_weights))
        .with_for_update()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Blueprint version not found.")
    if version.status != BlueprintVersionStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft blueprint versions can be approved.")

    topic_ids = [item.topic_id for item in version.topic_weights]
    topics = list(
        db.scalars(
            select(Topic).where(
                Topic.id.in_(topic_ids),
                Topic.workspace_id == workspace_id,
                Topic.subject_id == version.subject_id,
            )
        ).all()
    )
    if len(topics) != len(topic_ids) or sum(
        item.target_marks for item in version.topic_weights
    ) != version.total_marks:
        raise HTTPException(
            status_code=422,
            detail="Blueprint topic allocation no longer satisfies workspace and total-mark constraints.",
        )

    version.status = BlueprintVersionStatus.APPROVED
    version.approved_by = membership.user_id
    version.approved_at = datetime.now(UTC)
    record_audit_event(
        db,
        action="exam_blueprint.version_approved",
        resource_type="exam_blueprint_version",
        resource_id=str(version.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={
            "blueprint_id": str(blueprint_id),
            "version_number": version.version_number,
            "total_marks": version.total_marks,
        },
    )
    db.commit()
    return _load_blueprint(db, workspace_id, blueprint_id)
