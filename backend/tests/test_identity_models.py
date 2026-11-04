"""Persistence constraints for canonical workspace identity records."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import MembershipRole, MembershipStatus, User, Workspace, WorkspaceMembership


def test_workspace_membership_is_unique_and_identity_keys_are_normalized() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email=" Learner@Example.test ", display_name="Learner")
            workspace = Workspace(name="Campus", slug=" Campus ")
            session.add_all([user, workspace])
            session.flush()
            assert user.email == "learner@example.test"
            assert workspace.slug == "campus"

            session.add(
                WorkspaceMembership(
                    user=user,
                    workspace=workspace,
                    role=MembershipRole.STUDENT,
                    status=MembershipStatus.ACTIVE,
                )
            )
            session.commit()
            session.add(
                WorkspaceMembership(
                    user=user,
                    workspace=workspace,
                    role=MembershipRole.ADMIN,
                    status=MembershipStatus.ACTIVE,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
