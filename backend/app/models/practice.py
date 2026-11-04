"""Persistent student practice exams and server-authoritative attempts."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
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


class PracticeAttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"


class PracticeExam(Base):
    """Immutable practice assessment definition scoped to its student owner."""

    __tablename__ = "practice_exams"
    __table_args__ = (
        Index("ix_practice_exams_owner_subject", "workspace_id", "subject_id", "created_by"),
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
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    questions: Mapped[list["PracticeExamQuestion"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", order_by="PracticeExamQuestion.ordinal"
    )
    attempts: Mapped[list["PracticeAttempt"]] = relationship(back_populates="exam")


class PracticeExamQuestion(Base):
    """Frozen ordered reference to one immutable question version."""

    __tablename__ = "practice_exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "ordinal", name="uq_practice_exam_question_ordinal"),
        UniqueConstraint("exam_id", "question_version_id", name="uq_practice_exam_question_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_exams.id", ondelete="CASCADE"), nullable=False
    )
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    exam: Mapped[PracticeExam] = relationship(back_populates="questions")
    question_version: Mapped["QuestionVersion"] = relationship()


class PracticeAttempt(Base):
    """Durable timed attempt; the server clock is authoritative."""

    __tablename__ = "practice_attempts"
    __table_args__ = (
        Index("ix_practice_attempts_owner_status", "student_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_exams.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[PracticeAttemptStatus] = mapped_column(
        String(16), default=PracticeAttemptStatus.IN_PROGRESS, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_marks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exam: Mapped[PracticeExam] = relationship(back_populates="attempts")
    responses: Mapped[list["PracticeAttemptResponse"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class PracticeAttemptResponse(Base):
    """Latest autosaved response and deterministic marking outcome for one exam item."""

    __tablename__ = "practice_attempt_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "exam_question_id", name="uq_attempt_exam_question_response"),
        Index("ix_attempt_responses_attempt", "attempt_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_attempts.id", ondelete="CASCADE"), nullable=False
    )
    exam_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_exam_questions.id", ondelete="CASCADE"), nullable=False
    )
    response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    awarded_marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marking_status: Mapped[str] = mapped_column(String(24), default="saved", nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    attempt: Mapped[PracticeAttempt] = relationship(back_populates="responses")
