"""Reusable, versioned question-bank records with source provenance."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QuestionReviewStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class Question(Base):
    """Stable question identity scoped to a workspace, subject and owner."""

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_workspace_subject_owner", "workspace_id", "subject_id", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    versions: Mapped[list["QuestionVersion"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionVersion.version_number",
    )


class QuestionVersion(Base):
    """Immutable question content, answer key and source citation snapshot."""

    __tablename__ = "question_versions"
    __table_args__ = (
        UniqueConstraint("question_id", "version_number", name="uq_question_version_number"),
        Index("ix_question_versions_topic_status", "topic_id", "review_status"),
        Index("ix_question_versions_outcome", "learning_outcome_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    learning_outcome_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="SET NULL"), nullable=True
    )
    question_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    cognitive_level: Mapped[str] = mapped_column(String(16), nullable=False)
    source_citations: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    generation_model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_status: Mapped[QuestionReviewStatus] = mapped_column(
        String(16), default=QuestionReviewStatus.DRAFT, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    question: Mapped[Question] = relationship(back_populates="versions")
