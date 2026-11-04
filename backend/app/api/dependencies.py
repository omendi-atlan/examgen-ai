"""Reusable authentication and workspace-authorization dependencies."""

import hashlib
import time
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import (
    ApiRateLimitBucket,
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)

_bearer = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_current_user(
    credentials: BearerCredentials,
    db: DatabaseSession,
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
    db: DatabaseSession,
    current_user: Annotated[User, Depends(get_current_user)],
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
        membership: Annotated[
            WorkspaceMembership,
            Depends(get_workspace_membership),
        ],
    ) -> WorkspaceMembership:
        if membership.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient workspace role.")
        return membership

    return dependency


def enforce_auth_rate_limit(
    request: Request,
    db: DatabaseSession,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    include_client: bool = True,
) -> None:
    """Atomically enforce a shared fixed-window limit across API processes."""
    client_host = request.client.host if request.client else "unknown"
    client_component = client_host if include_client else "authenticated-subject"
    digest = hashlib.sha256(f"{scope}:{client_component}:{subject.casefold()}".encode()).hexdigest()
    now = int(time.time())
    window_start = (now // window_seconds) * window_seconds
    table = ApiRateLimitBucket.__table__
    dialect = db.get_bind().dialect.name
    insert_statement = (
        postgresql_insert(table) if dialect == "postgresql" else sqlite_insert(table)
    )
    statement = insert_statement.values(
        bucket_key=digest,
        window_start=window_start,
        request_count=1,
    ).on_conflict_do_update(
        index_elements=[table.c.bucket_key],
        set_={
            "window_start": window_start,
            "request_count": case(
                (table.c.window_start == window_start, table.c.request_count + 1),
                else_=1,
            ),
        },
    ).returning(table.c.request_count)
    count = db.scalar(statement)
    db.execute(delete(table).where(table.c.window_start < now - 86400))
    db.commit()
    if count is not None and count > limit:
        retry_after = window_start + window_seconds - now
        raise HTTPException(
            status_code=429,
            detail="Too many authentication requests. Please try again later.",
            headers={"Retry-After": str(max(1, retry_after))},
        )


def limit_login_attempts(
    request: Request, db: DatabaseSession
) -> None:
    """Limit credential attempts per client address across API instances."""
    enforce_auth_rate_limit(
        request,
        db,
        scope="login",
        subject="credentials",
        limit=10,
        window_seconds=900,
    )


def limit_registration_attempts(
    request: Request, db: DatabaseSession
) -> None:
    """Limit account creation attempts per client address across API instances."""
    enforce_auth_rate_limit(
        request,
        db,
        scope="registration",
        subject="accounts",
        limit=5,
        window_seconds=3600,
    )



def limit_document_upload_attempts(
    request: Request,
    db: DatabaseSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Limit authenticated source uploads per user and transport peer address."""
    enforce_auth_rate_limit(
        request,
        db,
        scope="document_upload_ip",
        subject="all",
        limit=60,
        window_seconds=3600,
    )
    enforce_auth_rate_limit(
        request,
        db,
        scope="document_upload_user",
        subject=str(current_user.id),
        limit=20,
        window_seconds=3600,
        include_client=False,
    )


def limit_question_generation_attempts(
    request: Request,
    db: DatabaseSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Limit paid AI generation to 10 requests/account/hour and 30 per peer/hour."""
    enforce_auth_rate_limit(
        request,
        db,
        scope="question_generation_ip",
        subject="all",
        limit=30,
        window_seconds=3600,
    )
    enforce_auth_rate_limit(
        request,
        db,
        scope="question_generation_account",
        subject=str(current_user.id),
        limit=10,
        window_seconds=3600,
        include_client=False,
    )
