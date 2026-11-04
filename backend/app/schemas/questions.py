"""Strict request and student-safe response contracts for the question bank."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionType = Literal[
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_blank",
    "short_answer",
    "long_answer",
    "numeric",
    "matching",
    "ordering",
    "programming",
    "diagram_interpretation",
    "diagram_construction",
]
Difficulty = Literal["easy", "medium", "hard"]
CognitiveLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class QuestionGenerationRequest(BaseModel):
    """Generate private practice questions from selected, already-extracted subject sources."""

    source_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    topic_id: UUID | None = None
    learning_outcome_id: UUID | None = None
    question_count: int = Field(default=10, ge=1, le=30)
    total_marks: int = Field(default=30, ge=1, le=300)
    question_types: list[QuestionType] = Field(
        default=["multiple_choice", "short_answer"], min_length=1, max_length=8
    )
    difficulty: Difficulty = "medium"
    cognitive_levels: list[CognitiveLevel] = Field(
        default=["remember", "understand", "apply"], min_length=1, max_length=6
    )

    @field_validator("source_version_ids")
    @classmethod
    def unique_sources(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Source versions must be unique.")
        return value

    @model_validator(mode="after")
    def validate_question_count_and_marks(self):
        if self.question_count > self.total_marks:
            raise ValueError("Question count cannot exceed total marks.")
        return self


class GeneratedQuestionInput(BaseModel):
    question_type: QuestionType
    stem: str = Field(min_length=10, max_length=5000)
    options: list[dict[str, str]] | None = Field(default=None, max_length=8)
    correct_answer: dict[str, object]
    explanation: str = Field(min_length=3, max_length=5000)
    marks: int = Field(ge=1, le=100)
    difficulty: Difficulty
    cognitive_level: CognitiveLevel
    source_segment_ids: list[UUID] = Field(min_length=1, max_length=12)

    @field_validator("stem", "explanation")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Question text and explanation cannot be blank.")
        return clean

    @model_validator(mode="after")
    def validate_options_and_answers(self):
        objective = self.question_type in {"multiple_choice", "multiple_select", "true_false"}
        if objective:
            if not self.options or not 2 <= len(self.options) <= 8:
                raise ValueError("Objective questions require 2 to 8 answer options.")
            option_ids = [item.get("id", "") for item in self.options]
            if any(not item.get("text", "").strip() for item in self.options):
                raise ValueError("Every answer option must contain readable text.")
            if len(option_ids) != len(set(option_ids)):
                raise ValueError("Answer option identifiers must be unique.")
            answer_ids = self.correct_answer.get("option_ids")
            if self.question_type == "multiple_select":
                if not isinstance(answer_ids, list) or not answer_ids or not set(answer_ids) <= set(option_ids):
                    raise ValueError("Multiple-select answers must reference valid option identifiers.")
            else:
                answer_id = self.correct_answer.get("option_id")
                if answer_id not in option_ids:
                    raise ValueError("Objective answer must reference a valid option identifier.")
        elif self.options:
            raise ValueError("Only objective questions may contain answer options.")
        if not self.correct_answer:
            raise ValueError("A private marking answer is required.")
        return self


class GeneratedQuestionEnvelope(BaseModel):
    questions: list[GeneratedQuestionInput] = Field(min_length=1, max_length=30)


class QuestionCitation(BaseModel):
    document_title: str
    original_filename: str
    version_number: int
    locator: str
    segment_id: UUID
    source_version_id: UUID


class QuestionVersionResponse(BaseModel):
    """Student-safe representation; correct answers and explanations are never returned here."""

    id: UUID
    version_number: int
    question_type: QuestionType
    stem: str
    options: list[dict[str, str]] | None
    marks: int
    difficulty: Difficulty
    cognitive_level: CognitiveLevel
    topic_id: UUID | None
    learning_outcome_id: UUID | None
    source_citations: list[QuestionCitation]
    review_status: str


class QuestionResponse(BaseModel):
    id: UUID
    subject_id: UUID
    current_version_number: int
    created_at: str
    versions: list[QuestionVersionResponse]


class QuestionGenerationResponse(BaseModel):
    created_count: int
    total_marks: int
    questions: list[QuestionResponse]
