"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: str
    email: str
    display_name: str
    role: str


# --------------------------------------------------------------------------
# Workspaces
# --------------------------------------------------------------------------

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(default="", max_length=64)
    module: str = Field(default="", max_length=255)
    institution: str = Field(default="", max_length=255)
    qualification: str = Field(default="", max_length=255)
    description: str = ""


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    module: str | None = None
    institution: str | None = None
    qualification: str | None = None
    description: str | None = None
    supplementary_enabled: bool | None = None


class WorkspaceOut(ORMModel):
    id: str
    name: str
    code: str
    module: str
    institution: str
    qualification: str
    description: str
    supplementary_enabled: bool
    created_at: datetime


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------

class DocumentOut(ORMModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    version: int
    kind: str
    status: str
    processing_status: str
    processing_notes: str
    page_count: int
    extracted_chars: int
    is_latest: bool
    sha256: str
    created_at: datetime


class ExtractedContentOut(ORMModel):
    id: str
    document_id: str
    ordinal: int
    heading: str
    kind: str
    text: str
    page: int
    provenance: str


class SufficiencyOut(ORMModel):
    id: str
    adequate: list
    partial: list
    missing: list
    missing_outcomes: list
    conflicts: list
    insufficient_types: list
    clarifications: list
    document_count: int
    total_chars: int
    verdict: str
    created_at: datetime


# --------------------------------------------------------------------------
# Topics
# --------------------------------------------------------------------------

class TopicUpdate(BaseModel):
    name: str | None = None
    summary: str | None = None
    needs_visual: str | None = None
    reviewed_by_student: bool | None = None


class OutcomeOut(ORMModel):
    id: str
    statement: str
    bloom: str
    covered: bool
    subtopic_id: str


class SubtopicOut(ORMModel):
    id: str
    name: str
    summary: str
    coverage: str
    outcomes: list[OutcomeOut] = []


class TopicOut(ORMModel):
    id: str
    name: str
    summary: str
    coverage: str
    coverage_notes: str
    needs_visual: str
    visual_rationale: str
    confidence: float
    reviewed_by_student: bool
    subtopics: list[SubtopicOut] = []


# --------------------------------------------------------------------------
# Visuals
# --------------------------------------------------------------------------

class VisualOut(ORMModel):
    id: str
    key: str
    title: str
    diagram_type: str
    requirement: str
    status: str
    version: int
    labels: list
    intended_use: str
    topic_id: str | None
    approved_at: datetime | None


class VisualDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


# --------------------------------------------------------------------------
# Blueprint
# --------------------------------------------------------------------------

class BlueprintCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    duration_minutes: int = Field(default=60, ge=5, le=600)
    total_marks: int = Field(default=100, ge=5, le=1000)
    question_count: int = Field(default=10, ge=1, le=200)
    difficulty: str = "intermediate"
    topic_ids: list[str] = []
    outcome_ids: list[str] = []
    difficulty_distribution: dict[str, int] = {}
    type_distribution: dict[str, int] = {}
    bloom_distribution: dict[str, int] = {}
    required_visual_keys: list[str] = []
    assessment_objectives: list[str] = []
    instructions: str = ""
    mode: str = "practice"


class BlueprintOut(ORMModel):
    id: str
    title: str
    duration_minutes: int
    total_marks: int
    question_count: int
    difficulty: str
    topic_ids: list
    difficulty_distribution: dict
    type_distribution: dict
    bloom_distribution: dict
    required_visual_keys: list
    assessment_objectives: list
    validation: dict
    is_valid: bool
    created_at: datetime


# --------------------------------------------------------------------------
# Examination
# --------------------------------------------------------------------------

class GenerateExamRequest(BaseModel):
    mode: str = "practice"
    use_llm: bool = False


class ExamQuestionView(BaseModel):
    """Student-facing question view.

    Deliberately excludes the answer key, marking rubric and explanations so
    the examination-taking surface can never leak them, regardless of mode.
    """

    question_id: str
    ordinal: int
    section: str
    qtype: str
    prompt: str
    instructions: str
    marks: int
    difficulty: str
    bloom: str
    options: list
    payload: dict
    visual: dict | None = None


class AuthoringQuestionView(ExamQuestionView):
    """Workspace-owner view used for authoring, previewing and marking.

    Includes the answer key, explanation and rubric. This is only ever returned
    by workspace-scoped authoring endpoints, never by an attempt endpoint.
    """

    expected_answer: str = ""
    explanation: str = ""
    rubrics: list = []


class ExamOut(ORMModel):
    id: str
    title: str
    subject_name: str
    module_name: str
    version: int
    mode: str
    status: str
    duration_minutes: int
    total_marks: int
    instructions: str
    sections: list
    moderation_status: str
    moderation_findings: list
    published_at: datetime | None


class ExamDetail(ExamOut):
    questions: list[AuthoringQuestionView] = []


class AttemptStartRequest(BaseModel):
    student_name: str = ""
    student_number: str = ""


class AttemptOut(ORMModel):
    id: str
    examination_id: str
    student_name: str
    student_number: str
    mode: str
    status: str
    started_at: datetime
    deadline_at: datetime | None
    submitted_at: datetime | None
    score: float | None
    max_score: float | None
    percentage: float | None
    feedback_released: bool
    attempt_no: int


class ResponseSave(BaseModel):
    question_id: str
    answer: dict[str, Any] = {}
    flagged: bool = False


class AutosaveRequest(BaseModel):
    responses: list[ResponseSave]


class AttemptState(BaseModel):
    attempt: AttemptOut
    examination: ExamOut
    questions: list[ExamQuestionView]
    responses: dict[str, dict]
    flags: dict[str, bool]
    server_time: datetime
    remaining_seconds: int | None


# --------------------------------------------------------------------------
# Moderation / marking / analytics
# --------------------------------------------------------------------------

class ModerationFinding(BaseModel):
    severity: str
    code: str
    message: str
    question_id: str | None = None


class ModerationOut(BaseModel):
    status: str
    findings: list[ModerationFinding]


class MarkingOut(ORMModel):
    id: str
    question_id: str
    awarded: float
    max_marks: float
    method: str
    rationale: str
    needs_human_review: bool
    reviewed: bool
    breakdown: list


class AttemptResult(BaseModel):
    attempt: AttemptOut
    markings: list[MarkingOut]
    analytics: dict
    memorandum: list[dict] | None = None


class AnalyticsOut(BaseModel):
    workspace_id: str
    attempts: int
    average_percentage: float | None
    by_topic: list[dict]
    by_outcome: list[dict]
    by_difficulty: list[dict]
    by_bloom: list[dict]
    repeated_mistakes: list[dict]
    mastery: dict
    recommendations: list[str]
    history: list[dict]
