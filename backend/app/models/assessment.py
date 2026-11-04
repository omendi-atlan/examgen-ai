"""Versioned examination blueprint domain models."""

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
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BlueprintVersionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class ExamBlueprint(Base):
    """Stable workspace-scoped blueprint identity with append-only versions."""

    __tablename__ = "exam_blueprints"
    __table_args__ = (
        Index("ix_exam_blueprints_workspace_updated", "workspace_id", "updated_at"),
        CheckConstraint("current_version_number >= 0", name="ck_exam_blueprint_current_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
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
    versions: Mapped[list["ExamBlueprintVersion"]] = relationship(
        back_populates="blueprint",
        cascade="all, delete-orphan",
        order_by="ExamBlueprintVersion.version_number",
    )


class ExamBlueprintVersion(Base):
    """Immutable blueprint configuration snapshot."""

    __tablename__ = "exam_blueprint_versions"
    __table_args__ = (
        UniqueConstraint("blueprint_id", "version_number", name="uq_blueprint_version_number"),
        Index("ix_blueprint_versions_subject_created", "subject_id", "created_at"),
        CheckConstraint("version_number > 0", name="ck_blueprint_version_number_positive"),
        CheckConstraint("duration_minutes BETWEEN 1 AND 600", name="ck_blueprint_duration_range"),
        CheckConstraint("total_marks BETWEEN 1 AND 1000", name="ck_blueprint_total_marks_range"),
        CheckConstraint("question_count BETWEEN 1 AND 200", name="ck_blueprint_question_count_range"),
        CheckConstraint("question_count <= total_marks", name="ck_blueprint_question_count_marks"),
        CheckConstraint("status IN ('draft', 'approved')", name="ck_blueprint_version_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprints.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cognitive_distribution: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    difficulty_distribution: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    question_type_distribution: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    status: Mapped[BlueprintVersionStatus] = mapped_column(
        SqlEnum(
            BlueprintVersionStatus,
            native_enum=False,
            length=16,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=BlueprintVersionStatus.DRAFT,
        nullable=False,
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
    blueprint: Mapped[ExamBlueprint] = relationship(back_populates="versions")
    outcome_weights: Mapped[list["BlueprintOutcomeWeight"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="BlueprintOutcomeWeight.learning_outcome_id",
    )
    topic_weights: Mapped[list["BlueprintTopicWeight"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="BlueprintTopicWeight.topic_id",
    )


class BlueprintTopicWeight(Base):
    """Exact topic mark allocation within an immutable blueprint version."""

    __tablename__ = "blueprint_topic_weights"
    __table_args__ = (
        UniqueConstraint("version_id", "topic_id", name="uq_blueprint_version_topic_weight"),
        Index("ix_blueprint_topic_weights_topic", "topic_id"),
        CheckConstraint("target_marks > 0", name="ck_blueprint_topic_target_marks_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    target_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[ExamBlueprintVersion] = relationship(back_populates="topic_weights")


class BlueprintOutcomeWeight(Base):
    """Exact learning-outcome mark allocation within a blueprint version."""

    __tablename__ = "blueprint_outcome_weights"
    __table_args__ = (
        UniqueConstraint("version_id", "learning_outcome_id", name="uq_blueprint_version_outcome_weight"),
        Index("ix_blueprint_outcome_weights_outcome", "learning_outcome_id"),
        CheckConstraint("target_marks > 0", name="ck_blueprint_outcome_target_marks_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="CASCADE"), nullable=False
    )
    learning_outcome_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=False
    )
    target_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[ExamBlueprintVersion] = relationship(back_populates="outcome_weights")
