"""Validated request and response contracts for visual intelligence and moderation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DiagramKindLiteral = Literal[
    "flowchart",
    "process",
    "tree",
    "network",
    "er_diagram",
    "uml_class",
    "bar_chart",
    "line_chart",
    "cycle",
    "table",
]


class VisualNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=240)
    value: float | None = None


class VisualEdgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=240)


class VisualSpecInput(BaseModel):
    """An explicit, author-supplied diagram specification."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    kind: DiagramKindLiteral
    nodes: list[VisualNodeInput] = Field(default_factory=list, max_length=40)
    edges: list[VisualEdgeInput] = Field(default_factory=list, max_length=80)
    columns: list[str] | None = Field(default=None, max_length=12)
    rows: list[list[str]] | None = Field(default=None, max_length=60)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Visual title cannot be blank.")
        return clean


class VisualAssetCreate(BaseModel):
    """Create a visual asset, either from an explicit spec or an auto-drafted scaffold."""

    requirement_item_id: UUID | None = None
    blueprint_version_id: UUID | None = None
    spec: VisualSpecInput | None = None

    @model_validator(mode="after")
    def require_a_source(self):
        if self.spec is None and self.requirement_item_id is None:
            raise ValueError(
                "Provide either an explicit 'spec' or a 'requirement_item_id' to auto-draft from."
            )
        if self.requirement_item_id is None and self.blueprint_version_id is None:
            raise ValueError("Provide a 'requirement_item_id' or a 'blueprint_version_id'.")
        return self


class VisualAssetVersionCreate(BaseModel):
    """Append a revised immutable version to an existing asset."""

    spec: VisualSpecInput


class VisualDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=10, max_length=2000)

    @field_validator("rationale")
    @classmethod
    def strip_rationale(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 10:
            raise ValueError("A decision rationale of at least 10 characters is required.")
        return clean


class VisualRequirementItemResponse(BaseModel):
    id: UUID
    topic_id: UUID
    topic_name: str
    requirement_level: str
    recommended_kind: str | None
    proposed_title: str
    rationale: str
    signals: dict[str, object]
    approved_asset_version_id: UUID | None = None


class VisualAssetVersionResponse(BaseModel):
    id: UUID
    version_number: int
    diagram_kind: str
    status: str
    alt_text: str
    validation_report: dict[str, object]
    svg_url: str
    created_at: datetime


class VisualAssetResponse(BaseModel):
    id: UUID
    title: str
    blueprint_version_id: UUID
    requirement_item_id: UUID | None
    current_version_number: int
    created_at: datetime
    versions: list[VisualAssetVersionResponse]


class VisualAssessmentResponse(BaseModel):
    id: UUID | None
    blueprint_version_id: UUID
    analyser_version: str | None
    essential_count: int
    beneficial_count: int
    unnecessary_count: int
    created_at: datetime | None
    items: list[VisualRequirementItemResponse]
    assets: list[VisualAssetResponse]


class ModerationFindingResponse(BaseModel):
    check: str
    severity: str
    message: str
    detail: dict[str, object]


class ModerationReportResponse(BaseModel):
    engine_version: str
    blueprint_version_id: UUID
    status: str
    can_publish: bool
    critical_count: int
    warning_count: int
    findings: list[ModerationFindingResponse]
