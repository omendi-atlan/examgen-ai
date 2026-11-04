"""Canonical SQLAlchemy models registered with the shared metadata."""

from app.models.assessment import (
    BlueprintOutcomeWeight,
    BlueprintTopicWeight,
    BlueprintVersionStatus,
    ExamBlueprint,
    ExamBlueprintVersion,
)

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
from app.models.identity import (
    ApiRateLimitBucket,
    AuditEvent,
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)

__all__ = [
    "AcademicDocument",
    "BlueprintOutcomeWeight",
    "BlueprintTopicWeight",
    "BlueprintVersionStatus",
    "ExamBlueprint",
    "ExamBlueprintVersion",
    "ApiRateLimitBucket",
    "AuditEvent",
    "ClassificationMethod",
    "DocumentExtraction",
    "DocumentExtractionReview",
    "DocumentTextSegment",
    "DocumentTopicClassification",
    "DocumentVersion",
    "ExtractionStatus",
    "LearningOutcome",
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
