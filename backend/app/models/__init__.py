"""Canonical SQLAlchemy models registered with the shared metadata."""

from app.models.academic import (
    AcademicDocument,
    ClassificationMethod,
    DocumentExtraction,
    DocumentExtractionReview,
    DocumentProcessingJob,
    DocumentTextSegment,
    DocumentTopicClassification,
    DocumentVersion,
    ExtractionJobStatus,
    ExtractionStatus,
    LearningOutcome,
    Subject,
    Topic,
)
from app.models.assessment import (\n    BlueprintOutcomeWeight,\n    BlueprintTopicWeight,\n    BlueprintVersionStatus,\n    ExamBlueprint,\n    ExamBlueprintVersion,\n)\nfrom app.models.identity import (
    ApiRateLimitBucket,
    AuditEvent,
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)

__all__ = [
    "AcademicDocument",\n    "BlueprintOutcomeWeight",\n    "BlueprintTopicWeight",\n    "BlueprintVersionStatus",\n    "ExamBlueprint",\n    "ExamBlueprintVersion",
    "ApiRateLimitBucket",
    "AuditEvent",
    "ClassificationMethod",
    "DocumentExtraction",
    "DocumentExtractionReview",
    "DocumentTextSegment",
    "DocumentTopicClassification",
    "DocumentVersion",
    "ExtractionStatus",\n    "LearningOutcome",
    "ExtractionJobStatus",
    "DocumentProcessingJob",
    "MembershipRole",
    "MembershipStatus",
    "Subject",
    "Topic",
    "User",
    "Workspace",
    "WorkspaceMembership",
]
