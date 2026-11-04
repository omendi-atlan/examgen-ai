"""Canonical SQLAlchemy models registered with the shared metadata."""

from app.models.academic import (
    AcademicDocument,
    ClassificationMethod,
    DocumentExtraction,
    DocumentTextSegment,
    DocumentTopicClassification,
    DocumentVersion,
    ExtractionStatus,
    Subject,
    Topic,
)
from app.models.identity import (
    AuditEvent,
    MembershipRole,
    MembershipStatus,
    User,
    Workspace,
    WorkspaceMembership,
)

__all__ = [
    "AcademicDocument",
    "AuditEvent",
    "ClassificationMethod",
    "DocumentExtraction",
    "DocumentTextSegment",
    "DocumentTopicClassification",
    "DocumentVersion",
    "ExtractionStatus",
    "MembershipRole",
    "MembershipStatus",
    "Subject",
    "Topic",
    "User",
    "Workspace",
    "WorkspaceMembership",
]
