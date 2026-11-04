from app.models.assessment import (
    BlueprintTopicWeight,
    BlueprintVersionStatus,
    ExamBlueprint,
    ExamBlueprintVersion,
)
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
