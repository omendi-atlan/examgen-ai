"""ORM models for EXAMGEN AI.

Entity model (see prompt section 16):

    User
      └── SubjectWorkspace            (strict academic isolation boundary)
            ├── AcademicDocument      (versioned uploads + provenance)
            │     └── ExtractedContent
            ├── Topic
            │     └── Subtopic
            │           └── LearningOutcome
            ├── VisualAsset           (versioned, approved diagrams)
            ├── Question              (versioned question-bank items)
            │     ├── AnswerKey
            │     └── MarkingRubric
            ├── ExaminationBlueprint
            └── Examination           (immutable published version)
                  ├── ExaminationAttempt
                  │     ├── StudentResponse
                  │     ├── Submission
                  │     └── MarkingRecord
                  └── PDFDeliverable

All identifiers are opaque UUID strings so they can be safely exposed in URLs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------
# Enumerations (stored as short strings for readability + portability)
# --------------------------------------------------------------------------

class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    CLASSIFIED = "classified"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class CoverageLevel(str, Enum):
    ADEQUATE = "adequate"
    PARTIAL = "partial"
    MISSING = "missing"


class VisualRequirement(str, Enum):
    ESSENTIAL = "essential"
    BENEFICIAL = "beneficial"
    UNNECESSARY = "unnecessary"


class VisualStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class QuestionType(str, Enum):
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    EXTENDED_RESPONSE = "extended_response"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    MATCHING = "matching"
    NUMERICAL = "numerical"
    FORMULA = "formula"
    ORDERING = "ordering"
    DIAGRAM_INTERPRETATION = "diagram_interpretation"
    DIAGRAM_LABELLING = "diagram_labelling"
    CASE_STUDY = "case_study"
    ESSAY = "essay"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYSE = "analyse"
    EVALUATE = "evaluate"
    CREATE = "create"


class ModerationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REQUIRES_REVIEW = "requires_review"
    REJECTED = "rejected"


class ExamMode(str, Enum):
    PRACTICE = "practice"
    FORMAL = "formal"


class ExamStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AttemptStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    MARKED = "marked"
    EXPIRED = "expired"


class MasteryLevel(str, Enum):
    NOT_ASSESSED = "not_assessed"
    REQUIRES_IMPROVEMENT = "requires_improvement"
    DEVELOPING = "developing"
    COMPETENT = "competent"
    STRONG = "strong_mastery"


class Provenance(str, Enum):
    COURSEWORK = "coursework"
    PREVIOUS_ASSESSMENT = "previous_assessment"
    QUESTION_BANK = "question_bank"
    SUPPLEMENTARY = "supplementary"
    GENERATED = "generated"


class PDFKind(str, Enum):
    MEMORANDUM = "memorandum"
    MASTERY_GUIDE = "mastery_guide"


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="student")

    workspaces: Mapped[list["SubjectWorkspace"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------
# Subject workspace — the isolation boundary
# --------------------------------------------------------------------------

class SubjectWorkspace(Base, TimestampMixin):
    __tablename__ = "subject_workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(64), default="")
    module: Mapped[str] = mapped_column(String(255), default="")
    institution: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    qualification: Mapped[str] = mapped_column(String(255), default="")
    supplementary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User] = relationship(back_populates="workspaces")
    documents: Mapped[list["AcademicDocument"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")
    visuals: Mapped[list["VisualAsset"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")
    blueprints: Mapped[list["ExaminationBlueprint"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")
    examinations: Mapped[list["Examination"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_workspace_owner_name"),)


class AcademicDocument(Base, TimestampMixin):
    __tablename__ = "academic_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32), default="coursework")
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.UPLOADED.value)
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.PENDING.value)
    processing_notes: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_chars: Mapped[int] = mapped_column(Integer, default=0)
    # Version lineage: a re-upload of the same logical document points at root.
    supersedes_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="documents")
    chunks: Mapped[list["ExtractedContent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan")


class ExtractedContent(Base, TimestampMixin):
    __tablename__ = "extracted_content"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("academic_documents.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(String(512), default="")
    kind: Mapped[str] = mapped_column(String(32), default="paragraph")
    text: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[str] = mapped_column(
        String(32), default=Provenance.COURSEWORK.value)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[AcademicDocument] = relationship(back_populates="chunks")


class SourceReference(Base, TimestampMixin):
    """Explicit provenance link: a generated artifact -> a source document."""

    __tablename__ = "source_references"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locator: Mapped[str] = mapped_column(String(512), default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(
        String(32), default=Provenance.COURSEWORK.value)


# --------------------------------------------------------------------------
# Academic hierarchy
# --------------------------------------------------------------------------

class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(512))
    # The classifier's own label, retained so student edits (renames, visual
    # overrides) survive reclassification.
    derived_name: Mapped[str] = mapped_column(String(512), default="", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    coverage: Mapped[str] = mapped_column(String(32), default=CoverageLevel.ADEQUATE.value)
    coverage_notes: Mapped[str] = mapped_column(Text, default="")
    needs_visual: Mapped[str] = mapped_column(
        String(32), default=VisualRequirement.UNNECESSARY.value)
    visual_rationale: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reviewed_by_student: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="topics")
    subtopics: Mapped[list["Subtopic"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan")


class Subtopic(Base, TimestampMixin):
    __tablename__ = "subtopics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    coverage: Mapped[str] = mapped_column(String(32), default=CoverageLevel.ADEQUATE.value)

    topic: Mapped[Topic] = relationship(back_populates="subtopics")
    outcomes: Mapped[list["LearningOutcome"]] = relationship(
        back_populates="subtopic", cascade="all, delete-orphan")


class LearningOutcome(Base, TimestampMixin):
    __tablename__ = "learning_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    subtopic_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subtopics.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(String(32), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    statement: Mapped[str] = mapped_column(Text)
    bloom: Mapped[str] = mapped_column(String(32), default=BloomLevel.UNDERSTAND.value)
    covered: Mapped[bool] = mapped_column(Boolean, default=True)

    subtopic: Mapped[Subtopic] = relationship(back_populates="outcomes")


# --------------------------------------------------------------------------
# Visual assets
# --------------------------------------------------------------------------

class VisualAsset(Base, TimestampMixin):
    __tablename__ = "visual_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    learning_outcome_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    diagram_type: Mapped[str] = mapped_column(String(64))
    requirement: Mapped[str] = mapped_column(
        String(32), default=VisualRequirement.BENEFICIAL.value)
    status: Mapped[str] = mapped_column(String(32), default=VisualStatus.PROPOSED.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    svg: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[list] = mapped_column(JSON, default=list)
    intended_use: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(
        String(32), default=Provenance.GENERATED.value)
    approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="visuals")


# --------------------------------------------------------------------------
# Examination blueprint
# --------------------------------------------------------------------------

class ExaminationBlueprint(Base, TimestampMixin):
    __tablename__ = "examination_blueprints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    total_marks: Mapped[int] = mapped_column(Integer, default=100)
    question_count: Mapped[int] = mapped_column(Integer, default=10)
    difficulty: Mapped[str] = mapped_column(String(32), default=Difficulty.INTERMEDIATE.value)
    topic_ids: Mapped[list] = mapped_column(JSON, default=list)
    outcome_ids: Mapped[list] = mapped_column(JSON, default=list)
    difficulty_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    type_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    bloom_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    required_visual_keys: Mapped[list] = mapped_column(JSON, default=list)
    assessment_objectives: Mapped[list] = mapped_column(JSON, default=list)
    instructions: Mapped[str] = mapped_column(Text, default="")
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="blueprints")


# --------------------------------------------------------------------------
# Question bank
# --------------------------------------------------------------------------

class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subtopic_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    learning_outcome_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visual_asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visual_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    qtype: Mapped[str] = mapped_column(String(32))
    difficulty: Mapped[str] = mapped_column(String(32), default=Difficulty.INTERMEDIATE.value)
    bloom: Mapped[str] = mapped_column(String(32), default=BloomLevel.UNDERSTAND.value)
    prompt: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text, default="")
    marks: Mapped[int] = mapped_column(Integer, default=1)
    options: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    acceptable_alternatives: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    common_errors: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[str] = mapped_column(
        String(32), default=Provenance.COURSEWORK.value)
    source_document_ids: Mapped[list] = mapped_column(JSON, default=list)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[str] = mapped_column(Text, default="")
    in_bank: Mapped[bool] = mapped_column(Boolean, default=True)

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="questions")
    answer_key: Mapped["AnswerKey | None"] = relationship(
        back_populates="question", uselist=False, cascade="all, delete-orphan")
    rubrics: Mapped[list["MarkingRubric"]] = relationship(
        back_populates="question", cascade="all, delete-orphan")


class AnswerKey(Base, TimestampMixin):
    __tablename__ = "answer_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("questions.id", ondelete="CASCADE"), unique=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    correct: Mapped[dict] = mapped_column(JSON, default=dict)
    acceptable: Mapped[list] = mapped_column(JSON, default=list)
    tolerance: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(64), default="")
    deterministic: Mapped[bool] = mapped_column(Boolean, default=True)

    question: Mapped[Question] = relationship(back_populates="answer_key")


class MarkingRubric(Base, TimestampMixin):
    __tablename__ = "marking_rubrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    criterion: Mapped[str] = mapped_column(Text)
    marks: Mapped[int] = mapped_column(Integer, default=1)
    guidance: Mapped[str] = mapped_column(Text, default="")
    partial_credit: Mapped[bool] = mapped_column(Boolean, default=True)

    question: Mapped[Question] = relationship(back_populates="rubrics")


# --------------------------------------------------------------------------
# Examination (immutable versioned publication)
# --------------------------------------------------------------------------

class Examination(Base, TimestampMixin):
    __tablename__ = "examinations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    blueprint_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    subject_name: Mapped[str] = mapped_column(String(255), default="")
    module_name: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    mode: Mapped[str] = mapped_column(String(32), default=ExamMode.PRACTICE.value)
    status: Mapped[str] = mapped_column(String(32), default=ExamStatus.DRAFT.value)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    total_marks: Mapped[int] = mapped_column(Integer, default=100)
    instructions: Mapped[str] = mapped_column(Text, default="")
    sections: Mapped[list] = mapped_column(JSON, default=list)
    question_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    visual_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    moderation_status: Mapped[str] = mapped_column(
        String(32), default=ModerationStatus.PENDING.value)
    moderation_findings: Mapped[list] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")

    workspace: Mapped[SubjectWorkspace] = relationship(back_populates="examinations")
    attempts: Mapped[list["ExaminationAttempt"]] = relationship(
        back_populates="examination", cascade="all, delete-orphan")
    pdfs: Mapped[list["PDFDeliverable"]] = relationship(
        back_populates="examination", cascade="all, delete-orphan")


class ExaminationAttempt(Base, TimestampMixin):
    __tablename__ = "examination_attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    examination_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("examinations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    student_id: Mapped[str] = mapped_column(String(32), index=True)
    student_name: Mapped[str] = mapped_column(String(255), default="")
    student_number: Mapped[str] = mapped_column(String(128), default="")
    mode: Mapped[str] = mapped_column(String(32), default=ExamMode.PRACTICE.value)
    status: Mapped[str] = mapped_column(String(32), default=AttemptStatus.IN_PROGRESS.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_released: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)

    examination: Mapped[Examination] = relationship(back_populates="attempts")
    responses: Mapped[list["StudentResponse"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan")
    markings: Mapped[list["MarkingRecord"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan")


class StudentResponse(Base, TimestampMixin):
    __tablename__ = "student_responses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("examination_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(32), index=True)
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    autosaved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempt: Mapped[ExaminationAttempt] = relationship(back_populates="responses")

    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),)


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("examination_attempts.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="manual")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    attempt: Mapped[ExaminationAttempt] = relationship(back_populates="submissions")


class MarkingRecord(Base, TimestampMixin):
    __tablename__ = "marking_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("examination_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(32), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    awarded: Mapped[float] = mapped_column(Float, default=0.0)
    max_marks: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(32), default="objective")
    rationale: Mapped[str] = mapped_column(Text, default="")
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    breakdown: Mapped[list] = mapped_column(JSON, default=list)

    attempt: Mapped[ExaminationAttempt] = relationship(back_populates="markings")


# --------------------------------------------------------------------------
# Deliverables
# --------------------------------------------------------------------------

class PDFDeliverable(Base, TimestampMixin):
    __tablename__ = "pdf_deliverables"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    examination_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("examinations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(1024))
    exam_version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    released: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    examination: Mapped[Examination] = relationship(back_populates="pdfs")


class ResourceSufficiencyReport(Base, TimestampMixin):
    __tablename__ = "resource_sufficiency_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    adequate: Mapped[list] = mapped_column(JSON, default=list)
    partial: Mapped[list] = mapped_column(JSON, default=list)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    missing_outcomes: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    insufficient_types: Mapped[list] = mapped_column(JSON, default=list)
    clarifications: Mapped[list] = mapped_column(JSON, default=list)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    total_chars: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(32), default="")


# --------------------------------------------------------------------------
# Subject assistant (grounded chat)
# --------------------------------------------------------------------------

class ChatSession(Base, TimestampMixin):
    """A persisted assistant conversation, scoped to one subject workspace.

    Conversations never span workspaces: the assistant can only ever cite
    material from the workspace that owns the session.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base, TimestampMixin):
    """One turn in a subject-assistant conversation.

    ``citations`` records the exact coursework excerpts an answer was grounded
    in so every claim remains traceable to a source document, and ``suggestions``
    carries follow-up prompts the student can act on.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(32), default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
