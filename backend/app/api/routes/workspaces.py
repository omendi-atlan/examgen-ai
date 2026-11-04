"""Tenant-scoped workspace operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_workspace_membership
from app.core.database import get_db
from app.models import (
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.schemas.identity import CreateWorkspaceRequest, WorkspaceResponse
from app.services.audit import record_audit_event

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: CreateWorkspaceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Create a workspace and its owner membership in one transaction."""
    workspace = Workspace(name=payload.name, slug=payload.slug)
    db.add(workspace)
    try:
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=current_user.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )
        record_audit_event(
            db,
            action="workspace.created",
            resource_type="workspace",
            resource_id=str(workspace.id),
            actor_user_id=current_user.id,
            workspace_id=workspace.id,
            event_data={"slug": workspace.slug},
        )
        db.commit()
        db.refresh(workspace)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Workspace slug is already in use.") from None
    return workspace


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Workspace]:
    """List only active workspaces in which the current user has active membership."""
    statement = (
        select(Workspace)
        .join(WorkspaceMembership)
        .where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE,
            Workspace.is_active.is_(True),
        )
        .order_by(Workspace.name)
    )
    return list(db.scalars(statement).all())


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def read_workspace(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    membership: WorkspaceMembership = Depends(get_workspace_membership),
) -> Workspace:
    """Return a workspace only to a user with active membership in that tenant."""
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace
