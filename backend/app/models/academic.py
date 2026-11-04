"""Canonical academic source, extraction, provenance and taxonomy models."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Float,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExtractionStatus(StrEnum):
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"
    EMPTY = "empty"
    FAILED = "failed"
    QUEUED = "queued"
    PROCESSING = "processing"


class ExtractionJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ClassificationMethod(StrEnum):
    HUMAN = "human"
    AI_SUGGESTED = "ai_suggested"


class AcademicDocument(Base):
    """Stable logical document identity; each uploaded revision is a separate version."""

    __tablename__ = "academic_documents"
    __table_args__ = (
        Index("ix_academic_documents_workspace_updated", "workspace_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number"
    )


class DocumentVersion(Base):
    """Immutable uploaded source revision with its provenance and content fingerprint."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("document_id", "sha256", name="uq_document_version_content"),
        Index("ix_document_versions_document_created", "document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(12), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(240), nullable=True)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    document: Mapped[AcademicDocument] = relationship(back_populates="versions")
    extraction: Mapped["DocumentExtraction | None"] = relationship(
        back_populates="version", cascade="all, delete-orphan", uselist=False
    )
    classifications: Mapped[list["DocumentTopicClassification"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class DocumentExtraction(Base):
    """One reproducible extraction record per immutable source version."""

    __tablename__ = "document_extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        SqlEnum(
            ExtractionStatus,
            native_enum=False,
            length=24,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    parser_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extraction_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quality_report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[DocumentVersion] = relationship(back_populates="extraction")
    segments: Mapped[list["DocumentTextSegment"]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan", order_by="DocumentTextSegment.ordinal"
    )


class DocumentTextSegment(Base):
    """Extracted text with a stable page/slide/paragraph locator for source citations."""

    __tablename__ = "document_text_segments"
    __table_args__ = (
        UniqueConstraint("extraction_id", "ordinal", name="uq_extraction_segment_ordinal"),
        Index("ix_document_segments_extraction", "extraction_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_extractions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    extraction: Mapped[DocumentExtraction] = relationship(back_populates="segments")


class Subject(Base):
    """Workspace-owned explicit subject taxonomy root."""

    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "normalized_name", name="uq_subject_workspace_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class Topic(Base):
    """Explicit topic nested under exactly one subject."""

    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("subject_id", "normalized_name", name="uq_topic_subject_name"),
        Index("ix_topics_workspace_subject", "workspace_id", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    subject: Mapped[Subject] = relationship(back_populates="topics")
    classifications: Mapped[list["DocumentTopicClassification"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class DocumentTopicClassification(Base):
    """Human-confirmed or explicitly labelled AI-suggested topic assignment."""

    __tablename__ = "document_topic_classifications"
    __table_args__ = (
        UniqueConstraint("version_id", "topic_id", name="uq_document_version_topic"),
        Index("ix_document_classifications_topic", "topic_id", "version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[ClassificationMethod] = mapped_column(
        SqlEnum(
            ClassificationMethod,
            native_enum=False,
            length=24,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=ClassificationMethod.HUMAN,
        nullable=False,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[DocumentVersion] = relationship(back_populates="classifications")
    topic: Mapped[Topic] = relationship(back_populates="classifications")


class DocumentProcessingJob(Base):
    """Durable processing work item bound to exactly one immutable source version."""

    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        Index("ix_document_processing_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[ExtractionJobStatus] = mapped_column(
        SqlEnum(
            ExtractionJobStatus,
            native_enum=False,
            length=24,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=ExtractionJobStatus.QUEUED,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    lease_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[DocumentVersion] = relationship()
