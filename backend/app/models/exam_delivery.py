"""Immutable examination papers and durable student attempt records."""

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


class ExamPaperMode(StrEnum):
    PRACTICE = "practice"
    SIMULATION = "simulation"


class ExamPaperStatus(StrEnum):
    PUBLISHED = "published"
    RETIRED = "retired"


class ExamAttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"


class AttemptMarkingMethod(StrEnum):
    OBJECTIVE = "objective"
    MANUAL = "manual"


class ExamPaper(Base):
    """Stable identity for a private practice paper or moderated cohort paper."""

    __tablename__ = "exam_papers"
    __table_args__ = (
        CheckConstraint("visibility IN ('private', 'cohort')", name="ck_exam_paper_visibility"),
        CheckConstraint("mode IN ('practice', 'simulation')", name="ck_exam_paper_mode"),
        Index("ix_exam_papers_workspace_subject", "workspace_id", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    blueprint_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default=ExamPaperMode.PRACTICE, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    versions: Mapped[list["ExamPaperVersion"]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="ExamPaperVersion.version_number",
    )


class ExamPaperVersion(Base):
    """Published immutable question order and duration snapshot."""

    __tablename__ = "exam_paper_versions"
    __table_args__ = (
        UniqueConstraint("paper_id", "version_number", name="uq_exam_paper_version"),
        CheckConstraint("version_number > 0", name="ck_exam_paper_version_positive"),
        CheckConstraint("duration_minutes BETWEEN 1 AND 600", name="ck_exam_duration_range"),
        CheckConstraint("total_marks > 0", name="ck_exam_total_marks_positive"),
        CheckConstraint("question_count > 0", name="ck_exam_question_count_positive"),
        CheckConstraint("status IN ('published', 'retired')", name="ck_exam_paper_version_status"),
        Index("ix_exam_paper_versions_blueprint", "blueprint_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    blueprint_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paper: Mapped[ExamPaper] = relationship(back_populates="versions")
    questions: Mapped[list["ExamPaperQuestion"]] = relationship(
        back_populates="paper_version",
        cascade="all, delete-orphan",
        order_by="ExamPaperQuestion.ordinal",
    )


class ExamPaperQuestion(Base):
    """Student-safe immutable question snapshot bound to one approved question version."""

    __tablename__ = "exam_paper_questions"
    __table_args__ = (
        UniqueConstraint("paper_version_id", "ordinal", name="uq_exam_paper_question_ordinal"),
        UniqueConstraint("paper_version_id", "question_version_id", name="uq_exam_paper_question_version"),
        CheckConstraint("ordinal > 0", name="ck_exam_paper_question_ordinal"),
        CheckConstraint("marks > 0", name="ck_exam_paper_question_marks"),
        Index("ix_exam_paper_questions_question_version", "question_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_paper_versions.id", ondelete="CASCADE"), nullable=False
    )
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    question_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    paper_version: Mapped[ExamPaperVersion] = relationship(back_populates="questions")


class ExamAttempt(Base):
    """Server-timed durable attempt; deadline and submission state are authoritative."""

    __tablename__ = "exam_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'submitted', 'expired')",
            name="ck_exam_attempt_status",
        ),
        Index("ix_exam_attempt_user_status", "candidate_user_id", "status"),
        Index("ix_exam_attempt_deadline_status", "deadline_at", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_paper_versions.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="in_progress", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responses: Mapped[list["AttemptResponse"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    submission: Mapped["AttemptSubmission | None"] = relationship(
        back_populates="attempt", uselist=False, cascade="all, delete-orphan"
    )


class AttemptResponse(Base):
    """Autosaved mutable draft response; frozen into AttemptSubmission on submit."""

    __tablename__ = "attempt_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "paper_question_id", name="uq_attempt_response_question"),
        CheckConstraint("revision > 0", name="ck_attempt_response_revision"),
        Index("ix_attempt_responses_attempt_saved", "attempt_id", "saved_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False
    )
    paper_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_paper_questions.id", ondelete="RESTRICT"), nullable=False
    )
    response: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    attempt: Mapped[ExamAttempt] = relationship(back_populates="responses")


class AttemptSubmission(Base):
    """Immutable final response snapshot and tamper-evident content digest."""

    __tablename__ = "attempt_submissions"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_attempt_submission_once"),
        Index("ix_attempt_submissions_submitted_at", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[ExamAttempt] = relationship(back_populates="submission")
    marks: Mapped[list["AttemptMark"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class AttemptMark(Base):
    """Deterministic objective result or pending manual-marking item."""

    __tablename__ = "attempt_marks"
    __table_args__ = (
        UniqueConstraint("submission_id", "paper_question_id", name="uq_attempt_mark_question"),
        CheckConstraint("max_marks > 0", name="ck_attempt_mark_max_positive"),
        CheckConstraint(
            "awarded_marks IS NULL OR (awarded_marks >= 0 AND awarded_marks <= max_marks)",
            name="ck_attempt_mark_awarded_range",
        ),
        CheckConstraint("marking_method IN ('objective', 'manual')", name="ck_attempt_mark_method"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attempt_submissions.id", ondelete="CASCADE"), nullable=False
    )
    paper_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_paper_questions.id", ondelete="RESTRICT"), nullable=False
    )
    awarded_marks: Mapped[float | None] = mapped_column(nullable=True)
    max_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    marking_method: Mapped[str] = mapped_column(String(16), nullable=False)
    feedback: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    marked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submission: Mapped[AttemptSubmission] = relationship(back_populates="marks")
