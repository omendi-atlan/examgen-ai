"""Validated request and response contracts for examination blueprints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

COGNITIVE_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
DIFFICULTY_LEVELS = {"easy", "medium", "hard"}
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


class BlueprintTopicWeightInput(BaseModel):
    topic_id: UUID
    target_marks: int = Field(gt=0, le=1000)


class BlueprintVersionCreate(BaseModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int = Field(gt=0, le=600)
    total_marks: int = Field(gt=0, le=1000)
    question_count: int = Field(gt=0, le=200)
    cognitive_distribution: dict[str, int]
    difficulty_distribution: dict[str, int]
    question_type_distribution: dict[str, int]
    topic_weights: list[BlueprintTopicWeightInput] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Blueprint title cannot be blank.")
        return clean

    @model_validator(mode="after")
    def validate_blueprint_constraints(self):
        """Require valid percentages, unique topic weights and exact mark coverage."""
        distributions = (
            ("cognitive_distribution", COGNITIVE_LEVELS),
            ("difficulty_distribution", DIFFICULTY_LEVELS),
            ("question_type_distribution", QUESTION_TYPES),
        )
        for field_name, allowed_values in distributions:
            distribution = getattr(self, field_name)
            if not distribution or set(distribution) - allowed_values:
                raise ValueError(f"{field_name} contains unsupported or missing categories.")
            if any(value < 0 or value > 100 for value in distribution.values()):
                raise ValueError(f"{field_name} values must be between 0 and 100.")
            if sum(distribution.values()) != 100:
                raise ValueError(f"{field_name} percentages must sum to exactly 100.")

        topic_ids = [item.topic_id for item in self.topic_weights]
        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("A topic may appear only once in the blueprint mark allocation.")
        if sum(item.target_marks for item in self.topic_weights) != self.total_marks:
            raise ValueError("Topic target marks must sum exactly to the blueprint total marks.")
        if self.question_count > self.total_marks:
            raise ValueError("Question count cannot exceed total marks.")
        return self


class BlueprintTopicWeightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic_id: UUID
    target_marks: int


class ExamBlueprintVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    subject_id: UUID
    title: str
    description: str | None
    duration_minutes: int
    total_marks: int
    question_count: int
    cognitive_distribution: dict[str, int]
    difficulty_distribution: dict[str, int]
    question_type_distribution: dict[str, int]
    status: str
    created_by: UUID
    approved_by: UUID | None
    approved_at: datetime | None
    topic_weights: list[BlueprintTopicWeightResponse]


class ExamBlueprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by: UUID
    current_version_number: int
    versions: list[ExamBlueprintVersionResponse]
