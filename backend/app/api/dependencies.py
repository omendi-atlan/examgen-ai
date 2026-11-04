"""Reusable authentication and workspace-authorization dependencies."""

from collections.abc import Callable
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import (
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve a valid bearer token to an active persisted user."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized from None

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise unauthorized
    return user


def get_workspace_membership(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceMembership:
    """Require active membership in the requested active workspace."""
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if workspace is None or not workspace.is_active:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return membership


def require_workspace_roles(
    *allowed_roles: MembershipRole,
) -> Callable:
    """Build a dependency that additionally enforces workspace roles."""

    def dependency(
        membership: WorkspaceMembership = Depends(get_workspace_membership),
    ) -> WorkspaceMembership:
        if membership.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient workspace role.")
        return membership

    return dependency
