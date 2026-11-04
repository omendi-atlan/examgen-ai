"""Canonical reusable question-bank models and immutable provenance."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class QuestionVersionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETIRED = "retired"


class Question(Base):
    """Stable question identity; edits append immutable version snapshots."""

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_workspace_subject_updated", "workspace_id", "subject_id", "updated_at"),
        Index("ix_questions_subject_owner", "subject_id", "created_by"),
        CheckConstraint("visibility IN ('private', 'cohort')", name="ck_question_visibility"),
        CheckConstraint("current_version_number >= 0", name="ck_question_current_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)
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
    """Immutable authored or AI-generated question content and server-only key."""

    __tablename__ = "question_versions"
    __table_args__ = (
        UniqueConstraint("question_id", "version_number", name="uq_question_version_number"),
        CheckConstraint("version_number > 0", name="ck_question_version_number_positive"),
        CheckConstraint("marks BETWEEN 1 AND 1000", name="ck_question_marks_range"),
        CheckConstraint(
            "question_type IN ('multiple_choice', 'multiple_select', 'true_false', "
            "'fill_blank', 'short_answer', 'long_answer', 'numeric', 'matching', "
            "'ordering', 'programming', 'diagram_interpretation', 'diagram_construction')",
            name="ck_question_type",
        ),
        CheckConstraint(
            "cognitive_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')",
            name="ck_question_cognitive_level",
        ),
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_question_difficulty"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected', 'retired')",
            name="ck_question_version_status",
        ),
        CheckConstraint("generation_method IN ('manual', 'ai')", name="ck_question_generation_method"),
        Index("ix_question_versions_topic_status", "topic_id", "status"),
        Index("ix_question_versions_outcome_status", "learning_outcome_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    learning_outcome_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    cognitive_level: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    response_schema: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    answer_key: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    model_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    visual_requirement: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    generation_method: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    generation_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[QuestionVersionStatus] = mapped_column(
        String(16), default=QuestionVersionStatus.DRAFT, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    question: Mapped[Question] = relationship(back_populates="versions")
    citations: Mapped[list["QuestionSourceCitation"]] = relationship(
        back_populates="question_version",
        cascade="all, delete-orphan",
        order_by="QuestionSourceCitation.created_at",
    )


class QuestionSourceCitation(Base):
    """Traceable link from a question version to an immutable extracted source segment."""

    __tablename__ = "question_source_citations"
    __table_args__ = (
        UniqueConstraint(
            "question_version_id", "source_segment_id", name="uq_question_source_segment"
        ),
        Index("ix_question_source_citations_segment", "source_segment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_versions.id", ondelete="CASCADE"), nullable=False
    )
    source_segment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_text_segments.id", ondelete="RESTRICT"), nullable=False
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False
    )
    source_locator: Mapped[str] = mapped_column(String(120), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    question_version: Mapped[QuestionVersion] = relationship(back_populates="citations")
