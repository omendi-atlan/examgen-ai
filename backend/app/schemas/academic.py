"""Validated contracts for academic source ingestion and explicit classification."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Subject name cannot be blank.")
        return result


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Topic name cannot be blank.")
        return result


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    subject_id: UUID
    name: str
    description: str | None


class ClassificationRequest(BaseModel):
    topic_ids: list[UUID] = Field(min_length=1, max_length=100)
    rationale: str | None = Field(default=None, max_length=4000)


class ClassificationResponse(BaseModel):
    id: UUID
    topic_id: UUID
    subject_id: UUID
    subject_name: str
    topic_name: str
    method: str
    rationale: str | None
    classified_by: UUID
    created_at: datetime


class ExtractionResponse(BaseModel):
    id: UUID
    status: str
    parser_name: str
    parser_version: str
    page_count: int | None
    character_count: int
    segment_count: int
    error_message: str | None
    quality_report: dict[str, object] = Field(default_factory=dict)


class DocumentVersionResponse(BaseModel):
    id: UUID
    version_number: int
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    source_type: str | None
    source_reference: str | None
    publisher: str | None
    published_on: date | None
    provenance: dict[str, object]
    uploaded_by: UUID
    created_at: datetime
    extraction: ExtractionResponse | None
    classifications: list[ClassificationResponse]


class DocumentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    current_version_number: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    versions: list[DocumentVersionResponse]


class TextSegmentResponse(BaseModel):
    id: UUID
    ordinal: int
    locator: str
    text: str
    metadata: dict[str, object]
