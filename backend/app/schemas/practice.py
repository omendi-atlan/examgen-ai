"""Contracts for private timed practice examinations and persistent attempts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class PracticeExamCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    duration_minutes: int = Field(ge=5, le=360)
    question_version_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Practice exam title cannot be blank.")
        return clean

    @field_validator("question_version_ids")
    @classmethod
    def unique_question_versions(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("A question version may appear only once in a practice exam.")
        return value


class PracticeExamResponse(BaseModel):
    id: UUID
    title: str
    duration_minutes: int
    total_marks: int
    question_count: int
    created_at: datetime


class PracticeAttemptSaveRequest(BaseModel):
    response: dict[str, object] = Field(max_length=40)


class PracticeAttemptQuestionResponse(BaseModel):
    exam_question_id: UUID
    question_version_id: UUID
    ordinal: int
    question_type: str
    stem: str
    options: list[dict[str, str]] | None
    marks: int
    response: dict[str, object] | None = None
    marking_status: str = "unanswered"
    awarded_marks: int | None = None
    is_correct: bool | None = None
    correct_answer: dict[str, object] | None = None
    explanation: str | None = None


class PracticeAttemptResponseModel(BaseModel):
    id: UUID
    exam_id: UUID
    exam_title: str
    status: str
    started_at: datetime
    expires_at: datetime
    submitted_at: datetime | None
    total_marks: int
    awarded_marks: int
    pending_review_count: int
    questions: list[PracticeAttemptQuestionResponse]
