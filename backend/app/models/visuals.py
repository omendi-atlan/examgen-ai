"""Visual intelligence: requirement analysis, versioned assets and approval gates.

An examination may only be published once every academically *essential* visual
requirement has an approved, versioned asset. Requirements, assets, immutable
asset versions and the append-only approval trail are all workspace scoped.
"""

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


class VisualRequirementLevel(StrEnum):
    ESSENTIAL = "essential"
    BENEFICIAL = "beneficial"
    UNNECESSARY = "unnecessary"


class DiagramKind(StrEnum):
    FLOWCHART = "flowchart"
    PROCESS = "process"
    TREE = "tree"
    NETWORK = "network"
    ER_DIAGRAM = "er_diagram"
    UML_CLASS = "uml_class"
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    CYCLE = "cycle"
    TABLE = "table"


class VisualAssetStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class VisualDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


def _enum_column(enum_type: type[StrEnum], length: int) -> SqlEnum:
    """Persist a StrEnum as a constrained, portable string column."""
    return SqlEnum(
        enum_type,
        native_enum=False,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class VisualRequirementAssessment(Base):
    """Immutable visual-needs analysis recorded against one blueprint version."""

    __tablename__ = "visual_requirement_assessments"
    __table_args__ = (
        UniqueConstraint("blueprint_version_id", name="uq_visual_assessment_blueprint_version"),
        Index("ix_visual_assessments_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    blueprint_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="CASCADE"), nullable=False
    )
    analyser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    essential_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    beneficial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unnecessary_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    items: Mapped[list["VisualRequirementItem"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="VisualRequirementItem.created_at",
    )


class VisualRequirementItem(Base):
    """Per-topic visual determination with the deterministic evidence behind it."""

    __tablename__ = "visual_requirement_items"
    __table_args__ = (
        UniqueConstraint("assessment_id", "topic_id", name="uq_visual_requirement_topic"),
        Index("ix_visual_requirement_items_level", "requirement_level"),
        CheckConstraint(
            "requirement_level IN ('essential', 'beneficial', 'unnecessary')",
            name="ck_visual_requirement_level",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visual_requirement_assessments.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    topic_name: Mapped[str] = mapped_column(String(160), nullable=False)
    requirement_level: Mapped[VisualRequirementLevel] = mapped_column(
        _enum_column(VisualRequirementLevel, 16), nullable=False
    )
    recommended_kind: Mapped[DiagramKind | None] = mapped_column(
        _enum_column(DiagramKind, 24), nullable=True
    )
    proposed_title: Mapped[str] = mapped_column(String(240), nullable=False)
    signals: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    assessment: Mapped[VisualRequirementAssessment] = relationship(back_populates="items")
    assets: Mapped[list["VisualAsset"]] = relationship(back_populates="requirement_item")


class VisualAsset(Base):
    """Stable identity for one versioned examination visual."""

    __tablename__ = "visual_assets"
    __table_args__ = (
        UniqueConstraint("blueprint_version_id", "fingerprint", name="uq_visual_asset_fingerprint"),
        Index("ix_visual_assets_workspace_subject", "workspace_id", "subject_id"),
        CheckConstraint("current_version_number >= 0", name="ck_visual_asset_current_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    blueprint_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprint_versions.id", ondelete="CASCADE"), nullable=False
    )
    requirement_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visual_requirement_items.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    requirement_item: Mapped[VisualRequirementItem | None] = relationship(back_populates="assets")
    versions: Mapped[list["VisualAssetVersion"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="VisualAssetVersion.version_number",
    )


class VisualAssetVersion(Base):
    """Immutable diagram specification and rendered SVG snapshot."""

    __tablename__ = "visual_asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_number", name="uq_visual_asset_version_number"),
        Index("ix_visual_asset_versions_status", "status"),
        CheckConstraint("version_number > 0", name="ck_visual_asset_version_positive"),
        CheckConstraint("status IN ('draft', 'approved', 'rejected')", name="ck_visual_asset_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visual_assets.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    diagram_kind: Mapped[DiagramKind] = mapped_column(_enum_column(DiagramKind, 24), nullable=False)
    spec: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    svg_markup: Mapped[str] = mapped_column(Text, nullable=False)
    validation_report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[VisualAssetStatus] = mapped_column(
        _enum_column(VisualAssetStatus, 16),
        default=VisualAssetStatus.DRAFT,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    asset: Mapped[VisualAsset] = relationship(back_populates="versions")
    decisions: Mapped[list["VisualAssetDecision"]] = relationship(
        back_populates="asset_version",
        cascade="all, delete-orphan",
        order_by="VisualAssetDecision.created_at",
    )


class VisualAssetDecision(Base):
    """Append-only approval or rejection record for one asset version."""

    __tablename__ = "visual_asset_decisions"
    __table_args__ = (
        Index("ix_visual_asset_decisions_version_created", "asset_version_id", "created_at"),
        CheckConstraint("decision IN ('approved', 'rejected')", name="ck_visual_asset_decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visual_asset_versions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[VisualDecision] = mapped_column(_enum_column(VisualDecision, 16), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    asset_version: Mapped[VisualAssetVersion] = relationship(back_populates="decisions")
