"""Validated question-bank authoring, generation and disclosure contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

QUESTION_TYPES = {
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
}
COGNITIVE_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
DIFFICULTIES = {"easy", "medium", "hard"}


class QuestionContentInput(BaseModel):
    question_type: str
    prompt: str = Field(min_length=5, max_length=12000)
    marks: int = Field(gt=0, le=1000)
    cognitive_level: str
    difficulty: str
    response_schema: dict[str, object] = Field(default_factory=dict)
    answer_key: dict[str, object] | None = None
    model_answer: str | None = Field(default=None, max_length=12000)
    explanation: str | None = Field(default=None, max_length=12000)
    rubric: dict[str, object] | None = None
    visual_requirement: dict[str, object] | None = None
    source_segment_ids: list[UUID] = Field(min_length=1, max_length=20)

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, value: str) -> str:
        result = value.strip()
        if len(result) < 5:
            raise ValueError("Question prompt must contain meaningful text.")
        return result

    @model_validator(mode="after")
    def validate_question_contract(self):
        if self.question_type not in QUESTION_TYPES:
            raise ValueError("Unsupported question type.")
        if self.cognitive_level not in COGNITIVE_LEVELS:
            raise ValueError("Unsupported cognitive level.")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("Unsupported question difficulty.")
        if len(self.source_segment_ids) != len(set(self.source_segment_ids)):
            raise ValueError("A source segment may be cited only once per question.")
        if self.answer_key is None:
            raise ValueError("An answer key or marking expectation is required.")

        answer = self.answer_key
        schema = self.response_schema
        if self.question_type in {"multiple_choice", "multiple_select"}:
            options = schema.get("options")
            if not isinstance(options, list) or not 2 <= len(options) <= 8:
                raise ValueError("Objective choice questions require between 2 and 8 options.")
            option_ids = {
                item.get("id")
                for item in options
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and isinstance(item.get("label"), str)
                and item["label"].strip()
            }
            if len(option_ids) != len(options):
                raise ValueError("Every option requires a unique id and non-empty label.")
            if self.question_type == "multiple_choice":
                if answer.get("correct_option_id") not in option_ids:
                    raise ValueError("The correct option must reference one supplied option.")
            else:
                correct = answer.get("correct_option_ids")
                if (
                    not isinstance(correct, list)
                    or not correct
                    or not set(correct).issubset(option_ids)
                ):
                    raise ValueError("Multiple-select answer keys must reference valid option ids.")
        elif self.question_type == "true_false":
            if not isinstance(answer.get("correct_value"), bool):
                raise ValueError("True/false questions require a boolean correct_value.")
        elif self.question_type == "fill_blank":
            accepted = answer.get("accepted_answers")
            if not isinstance(accepted, list) or not accepted or not all(
                isinstance(item, str) and item.strip() for item in accepted
            ):
                raise ValueError("Fill-in questions require at least one accepted answer.")
        elif self.question_type == "numeric":
            value = answer.get("value")
            tolerance = answer.get("tolerance", 0)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError("Numeric answer keys require a numeric value.")
            if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
                raise ValueError("Numeric tolerance must be a non-negative number.")
        elif self.question_type in {"short_answer", "long_answer", "programming"}:
            if not isinstance(self.rubric, dict):
                raise ValueError("Written/programming questions require an explicit marking rubric.")
            criteria = self.rubric.get("criteria")
            if not isinstance(criteria, list) or not criteria:
                raise ValueError("Rubrics require at least one marking criterion.")
            criterion_marks = [
                item.get("marks")
                for item in criteria
                if isinstance(item, dict) and isinstance(item.get("marks"), int)
            ]
            if len(criterion_marks) != len(criteria) or sum(criterion_marks) != self.marks:
                raise ValueError("Rubric criterion marks must sum exactly to the question marks.")
        elif self.question_type == "matching":
            if not isinstance(schema.get("left_items"), list) or not isinstance(
                schema.get("right_items"), list
            ) or not isinstance(answer.get("matches"), list):
                raise ValueError("Matching questions require left/right items and keyed matches.")
        elif self.question_type == "ordering":
            if not isinstance(schema.get("items"), list) or not isinstance(
                answer.get("ordered_ids"), list
            ):
                raise ValueError("Ordering questions require items and an ordered answer key.")
        elif self.question_type in {"diagram_interpretation", "diagram_construction"}:
            visual = self.visual_requirement
            if not isinstance(visual, dict) or not isinstance(visual.get("description"), str):
                raise ValueError("Diagram questions require a specific visual requirement brief.")
        return self


class QuestionCreate(BaseModel):
    subject_id: UUID
    topic_id: UUID
    learning_outcome_id: UUID
    visibility: Literal["private", "cohort"] = "private"
    content: QuestionContentInput


class QuestionVersionAppend(BaseModel):
    topic_id: UUID
    learning_outcome_id: UUID
    content: QuestionContentInput


class QuestionGenerationRequest(BaseModel):
    source_version_ids: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator("source_version_ids")
    @classmethod
    def unique_sources(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("A source version may be selected only once.")
        return value


class QuestionSourceCitationResponse(BaseModel):
    id: UUID
    source_segment_id: UUID
    source_version_id: UUID
    source_locator: str
    excerpt: str | None
    relevance_note: str | None


class QuestionVersionPublicResponse(BaseModel):
    id: UUID
    version_number: int
    topic_id: UUID
    learning_outcome_id: UUID
    question_type: str
    prompt: str
    marks: int
    cognitive_level: str
    difficulty: str
    response_schema: dict[str, object]
    status: str
    citations: list[QuestionSourceCitationResponse]


class QuestionVersionAuthoringResponse(QuestionVersionPublicResponse):
    answer_key: dict[str, object] | None
    model_answer: str | None
    explanation: str | None
    rubric: dict[str, object] | None
    visual_requirement: dict[str, object] | None
    generation_method: str
    generation_model: str | None
    content_fingerprint: str
    created_by: UUID
    approved_by: UUID | None
    approved_at: datetime | None


class QuestionResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    subject_id: UUID
    created_by: UUID
    visibility: str
    current_version_number: int
    created_at: datetime
    updated_at: datetime
    versions: list[QuestionVersionPublicResponse]


class QuestionAuthoringResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    subject_id: UUID
    created_by: UUID
    visibility: str
    current_version_number: int
    created_at: datetime
    updated_at: datetime
    versions: list[QuestionVersionAuthoringResponse]


class QuestionGenerationResponse(BaseModel):
    blueprint_version_id: UUID
    generated_count: int
    total_marks: int
    questions: list[QuestionAuthoringResponse]
