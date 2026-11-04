"""Student-safe practice examination and attempt contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PracticeExamCreate(BaseModel):
    blueprint_version_id: UUID
    question_ids: list[UUID] = Field(min_length=1, max_length=30)
    title: str | None = Field(default=None, max_length=240)

    @field_validator("question_ids")
    @classmethod
    def unique_question_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("A question may appear only once in a practice examination.")
        return value


class PracticeExamResponse(BaseModel):
    id: UUID
    subject_id: UUID
    title: str
    mode: str
    visibility: str
    current_version_number: int
    version_id: UUID
    duration_minutes: int
    total_marks: int
    question_count: int
    created_at: datetime


class AttemptStartResponse(BaseModel):
    attempt_id: UUID
    status: str
    started_at: datetime
    deadline_at: datetime
    paper_version_id: UUID


class AttemptCitation(BaseModel):
    source_locator: str
    excerpt: str | None


class AttemptQuestionResponse(BaseModel):
    id: UUID
    ordinal: int
    question_version_id: UUID
    question_type: str
    prompt: str
    marks: int
    cognitive_level: str
    difficulty: str
    response_schema: dict[str, object]
    citations: list[AttemptCitation]


class AttemptResponseValue(BaseModel):
    response: dict[str, object]
    revision: int
    saved_at: datetime


class ExamAttemptResponse(BaseModel):
    attempt_id: UUID
    paper_id: UUID
    paper_version_id: UUID
    title: str
    mode: str
    status: str
    started_at: datetime
    deadline_at: datetime
    submitted_at: datetime | None
    total_marks: int
    questions: list[AttemptQuestionResponse]
    responses: dict[str, AttemptResponseValue]


class AttemptSaveRequest(BaseModel):
    response: dict[str, object] = Field(max_length=40)


class AttemptSaveResponse(BaseModel):
    paper_question_id: UUID
    revision: int
    saved_at: datetime
    attempt_status: str


class AttemptSubmitResponse(BaseModel):
    attempt_id: UUID
    status: str
    submitted_at: datetime
    total_marks: int
    objective_score: float
    pending_manual_marks: int
    already_submitted: bool = False


class AttemptResultItem(BaseModel):
    paper_question_id: UUID
    ordinal: int
    max_marks: int
    awarded_marks: float | None
    marking_method: str
    is_correct: bool | None
    feedback: dict[str, object]
    correct_answer: dict[str, object] | None = None
    model_answer: str | None = None
    explanation: str | None = None


class AttemptResultResponse(BaseModel):
    attempt_id: UUID
    submitted_at: datetime
    objective_score: float
    total_marks: int
    pending_manual_marks: int
    items: list[AttemptResultItem]


class PracticeExamListResponse(BaseModel):
    items: list[PracticeExamResponse]
