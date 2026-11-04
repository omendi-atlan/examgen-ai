"""Registration, login and current-user endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, limit_login_attempts, limit_registration_attempts
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.identity import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.audit import record_audit_event

router = APIRouter(prefix="/auth", tags=["identity"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_registration_attempts)],
)
def register(payload: RegisterRequest, db: DatabaseSession) -> User:
    """Create a user account; passwords are never stored or returned in plaintext."""
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        record_audit_event(
            db,
            action="identity.registered",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=user.id,
        )
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit_login_attempts)],
)
def login(payload: LoginRequest, db: DatabaseSession) -> TokenResponse:
    """Authenticate credentials and return a short-lived signed access token."""
    user = db.scalar(select(User).where(User.email == payload.email))
    if (
        user is None
        or not user.is_active
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user.id)
    record_audit_event(
        db,
        action="identity.login_succeeded",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    db.commit()
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: AuthenticatedUser) -> User:
    """Return the authenticated user's public profile."""
    return current_user
