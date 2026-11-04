"""Examination moderation: publication gates for visual and question readiness.

The moderator report is computed from persisted facts, never from browser input.
It answers one operational question — *may this blueprint version be published?* —
and lists the exact findings that block or qualify publication.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BlueprintVersionStatus,
    ExamBlueprintVersion,
    Question,
    QuestionReviewStatus,
    QuestionVersion,
    Topic,
    VisualAsset,
    VisualAssetStatus,
    VisualAssetVersion,
    VisualRequirementAssessment,
    VisualRequirementLevel,
)

MODERATION_ENGINE_VERSION = "moderation-engine-v1"

STATUS_APPROVED = "approved"
STATUS_REQUIRES_REVIEW = "requires_review"
STATUS_REJECTED = "rejected"


@dataclass
class Finding:
    """One actionable moderation finding."""

    check: str
    severity: str  # critical | warning | info
    message: str
    detail: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {"check": self.check, "severity": self.severity, "message": self.message, "detail": self.detail}


@dataclass
class ModerationReport:
    status: str
    can_publish: bool
    findings: list[Finding]

    def as_dict(self) -> dict[str, object]:
        return {
            "engine_version": MODERATION_ENGINE_VERSION,
            "status": self.status,
            "can_publish": self.can_publish,
            "critical_count": sum(1 for f in self.findings if f.severity == "critical"),
            "warning_count": sum(1 for f in self.findings if f.severity == "warning"),
            "findings": [finding.as_dict() for finding in self.findings],
        }


def build_moderation_report(db: Session, version: ExamBlueprintVersion) -> ModerationReport:
    """Evaluate a blueprint version against the visual and question publication gates."""
    findings: list[Finding] = []

    if version.status != BlueprintVersionStatus.APPROVED:
        findings.append(
            Finding(
                check="blueprint_approved",
                severity="critical",
                message="The blueprint version must be approved before publication.",
                detail={"status": str(version.status)},
            )
        )

    _check_visuals(db, version, findings)
    _check_question_coverage(db, version, findings)

    if any(finding.severity == "critical" for finding in findings):
        status = STATUS_REJECTED
    elif any(finding.severity == "warning" for finding in findings):
        status = STATUS_REQUIRES_REVIEW
    else:
        status = STATUS_APPROVED
        if not findings:
            findings.append(
                Finding(
                    check="overall",
                    severity="info",
                    message="All moderation gates passed; the examination may be published.",
                )
            )
    return ModerationReport(status=status, can_publish=status == STATUS_APPROVED, findings=findings)


def _check_visuals(db: Session, version: ExamBlueprintVersion, findings: list[Finding]) -> None:
    assessment = db.scalar(
        select(VisualRequirementAssessment).where(
            VisualRequirementAssessment.blueprint_version_id == version.id
        )
    )
    if assessment is None:
        findings.append(
            Finding(
                check="visual_requirements_analysed",
                severity="critical",
                message="Visual requirements have not been analysed for this blueprint version.",
            )
        )
        return

    items = list(assessment.items)
    essential = [item for item in items if item.requirement_level == VisualRequirementLevel.ESSENTIAL]
    beneficial = [item for item in items if item.requirement_level == VisualRequirementLevel.BENEFICIAL]

    approved_topic_ids = set(
        db.scalars(
            select(VisualAsset.requirement_item_id)
            .join(VisualAssetVersion, VisualAssetVersion.asset_id == VisualAsset.id)
            .where(
                VisualAsset.blueprint_version_id == version.id,
                VisualAsset.requirement_item_id.is_not(None),
                VisualAssetVersion.status == VisualAssetStatus.APPROVED,
            )
        ).all()
    )

    unapproved_essential = [item for item in essential if item.id not in approved_topic_ids]
    if unapproved_essential:
        findings.append(
            Finding(
                check="essential_visuals_approved",
                severity="critical",
                message=(
                    f"{len(unapproved_essential)} essential visual requirement(s) lack an approved, "
                    "versioned asset; publication is blocked."
                ),
                detail={
                    "unapproved": [
                        {"topic_id": str(item.topic_id), "topic": item.topic_name, "kind": str(item.recommended_kind or "")}
                        for item in unapproved_essential
                    ]
                },
            )
        )
    elif essential:
        findings.append(
            Finding(
                check="essential_visuals_approved",
                severity="info",
                message=f"All {len(essential)} essential visual requirement(s) have approved assets.",
            )
        )

    unapproved_beneficial = [item for item in beneficial if item.id not in approved_topic_ids]
    if unapproved_beneficial:
        findings.append(
            Finding(
                check="beneficial_visuals",
                severity="warning",
                message=(
                    f"{len(unapproved_beneficial)} beneficial visual requirement(s) remain unapproved; "
                    "publication is permitted but review is recommended."
                ),
                detail={"unapproved": [item.topic_name for item in unapproved_beneficial]},
            )
        )

    unvalidated = db.scalar(
        select(func.count())
        .select_from(VisualAssetVersion)
        .join(VisualAsset, VisualAsset.id == VisualAssetVersion.asset_id)
        .where(
            VisualAsset.blueprint_version_id == version.id,
            VisualAssetVersion.status == VisualAssetStatus.APPROVED,
            VisualAssetVersion.validation_report["valid"].as_boolean().is_(False),
        )
    )
    if unvalidated:
        findings.append(
            Finding(
                check="visual_validation",
                severity="critical",
                message="An approved visual failed structural validation and must be corrected.",
                detail={"count": int(unvalidated)},
            )
        )


def _check_question_coverage(db: Session, version: ExamBlueprintVersion, findings: list[Finding]) -> None:
    topic_ids = [weight.topic_id for weight in version.topic_weights]
    if not topic_ids:
        findings.append(
            Finding(
                check="topic_coverage",
                severity="critical",
                message="The blueprint has no topic allocations.",
            )
        )
        return

    rows = list(
        db.execute(
            select(QuestionVersion.topic_id, QuestionVersion.marks)
            .join(Question, Question.id == QuestionVersion.question_id)
            .where(
                Question.workspace_id == version.blueprint.workspace_id,
                Question.subject_id == version.subject_id,
                QuestionVersion.topic_id.in_(topic_ids),
                QuestionVersion.review_status == QuestionReviewStatus.APPROVED,
            )
        ).all()
    )
    approved_marks = sum(int(marks) for _, marks in rows)
    covered_topics = {topic_id for topic_id, _ in rows}
    missing_topics = [topic_id for topic_id in topic_ids if topic_id not in covered_topics]

    if missing_topics:
        names = list(
            db.scalars(select(Topic.name).where(Topic.id.in_(missing_topics))).all()
        )
        findings.append(
            Finding(
                check="topic_coverage",
                severity="critical",
                message=(
                    f"{len(missing_topics)} blueprint topic(s) have no approved questions."
                ),
                detail={"missing_topics": names},
            )
        )
    else:
        findings.append(
            Finding(
                check="topic_coverage",
                severity="info",
                message=f"All {len(topic_ids)} blueprint topic(s) have approved questions.",
            )
        )

    if approved_marks < version.total_marks:
        findings.append(
            Finding(
                check="question_marks_sufficient",
                severity="critical",
                message=(
                    f"Approved questions provide {approved_marks} of the {version.total_marks} "
                    "marks the blueprint requires."
                ),
                detail={"approved_marks": approved_marks, "required_marks": version.total_marks},
            )
        )
    else:
        findings.append(
            Finding(
                check="question_marks_sufficient",
                severity="info",
                message=f"Approved questions cover all topics and provide {approved_marks} marks.",
            )
        )
