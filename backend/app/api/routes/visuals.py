"""Visual requirement analysis, versioned visual assets and moderation gates."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_workspace_roles
from app.core.database import get_db
from app.models import (
    DiagramKind,
    ExamBlueprint,
    ExamBlueprintVersion,
    LearningOutcome,
    MembershipRole,
    Topic,
    VisualAsset,
    VisualAssetDecision,
    VisualAssetStatus,
    VisualAssetVersion,
    VisualDecision,
    VisualRequirementAssessment,
    VisualRequirementItem,
    VisualRequirementLevel,
    WorkspaceMembership,
)
from app.schemas.visuals import (
    ModerationReportResponse,
    VisualAssessmentResponse,
    VisualAssetCreate,
    VisualAssetResponse,
    VisualAssetVersionCreate,
    VisualAssetVersionResponse,
    VisualDecisionRequest,
    VisualRequirementItemResponse,
)
from app.services.audit import record_audit_event
from app.services.moderation import build_moderation_report
from app.services.visual_intelligence import (
    VISUAL_ANALYSER_VERSION,
    VisualSpecInvalid,
    build_alt_text,
    build_auto_draft_spec,
    determine_requirement,
    render_svg,
    validate_spec,
)

router = APIRouter(tags=["visual-intelligence"])
DatabaseSession = Annotated[Session, Depends(get_db)]
WorkspaceEditor = Annotated[
    WorkspaceMembership,
    Depends(
        require_workspace_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.EXAMINER,
            MembershipRole.MODERATOR,
        )
    ),
]
WorkspaceApprover = Annotated[
    WorkspaceMembership,
    Depends(
        require_workspace_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.MODERATOR,
        )
    ),
]


def _load_version(db: Session, workspace_id: UUID, blueprint_id: UUID, version_id: UUID) -> ExamBlueprintVersion:
    version = db.scalar(
        select(ExamBlueprintVersion)
        .join(ExamBlueprint, ExamBlueprint.id == ExamBlueprintVersion.blueprint_id)
        .where(
            ExamBlueprint.id == blueprint_id,
            ExamBlueprint.workspace_id == workspace_id,
            ExamBlueprintVersion.id == version_id,
        )
        .options(
            selectinload(ExamBlueprintVersion.topic_weights),
            selectinload(ExamBlueprintVersion.blueprint),
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Examination blueprint version not found.")
    return version


def _load_asset(db: Session, workspace_id: UUID, asset_id: UUID) -> VisualAsset:
    asset = db.scalar(
        select(VisualAsset)
        .where(VisualAsset.id == asset_id, VisualAsset.workspace_id == workspace_id)
        .options(selectinload(VisualAsset.versions))
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Visual asset not found.")
    return asset


def _svg_url(workspace_id: UUID, asset: VisualAsset, version: VisualAssetVersion) -> str:
    return (
        f"/api/v1/workspaces/{workspace_id}/visuals/assets/{asset.id}"
        f"/versions/{version.id}/svg"
    )


def _asset_response(workspace_id: UUID, asset: VisualAsset) -> VisualAssetResponse:
    return VisualAssetResponse(
        id=asset.id,
        title=asset.title,
        blueprint_version_id=asset.blueprint_version_id,
        requirement_item_id=asset.requirement_item_id,
        current_version_number=asset.current_version_number,
        created_at=asset.created_at,
        versions=[
            VisualAssetVersionResponse(
                id=version.id,
                version_number=version.version_number,
                diagram_kind=str(version.diagram_kind),
                status=str(version.status),
                alt_text=version.alt_text,
                validation_report=version.validation_report,
                svg_url=_svg_url(workspace_id, asset, version),
                created_at=version.created_at,
            )
            for version in asset.versions
        ],
    )


def _approved_asset_version_ids(db: Session, version_id: UUID) -> dict[UUID, UUID]:
    rows = db.execute(
        select(VisualAsset.requirement_item_id, VisualAssetVersion.id)
        .join(VisualAssetVersion, VisualAssetVersion.asset_id == VisualAsset.id)
        .where(
            VisualAsset.blueprint_version_id == version_id,
            VisualAsset.requirement_item_id.is_not(None),
            VisualAssetVersion.status == VisualAssetStatus.APPROVED,
        )
        .order_by(VisualAssetVersion.version_number)
    ).all()
    approved: dict[UUID, UUID] = {}
    for requirement_item_id, asset_version_id in rows:
        approved[requirement_item_id] = asset_version_id
    return approved


@router.post(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/visuals/analyse",
    response_model=VisualAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyse_visual_requirements(
    workspace_id: UUID,
    blueprint_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    membership: WorkspaceEditor,
    force: bool = False,
) -> VisualAssessmentResponse:
    """Determine the visual requirements of a blueprint version from its topics.

    Analysis is idempotent; pass ``force=true`` to recompute after taxonomy changes.
    """
    version = _load_version(db, workspace_id, blueprint_id, version_id)
    existing = db.scalar(
        select(VisualRequirementAssessment).where(
            VisualRequirementAssessment.blueprint_version_id == version.id
        )
    )
    if existing is not None and not force:
        return _assessment_response(db, workspace_id, version, existing)
    if existing is not None:
        db.delete(existing)
        db.flush()

    topic_ids = [weight.topic_id for weight in version.topic_weights]
    topics = list(
        db.scalars(
            select(Topic).where(Topic.id.in_(topic_ids), Topic.workspace_id == workspace_id)
        ).all()
    )
    if not topics:
        raise HTTPException(
            status_code=422,
            detail="The blueprint version has no topics to analyse.",
        )
    outcome_counts = {
        topic_id: count
        for topic_id, count in db.execute(
            select(LearningOutcome.topic_id, func.count())
            .where(LearningOutcome.topic_id.in_(topic_ids))
            .group_by(LearningOutcome.topic_id)
        ).all()
    }

    assessment = VisualRequirementAssessment(
        workspace_id=workspace_id,
        subject_id=version.subject_id,
        blueprint_version_id=version.id,
        analyser_version=VISUAL_ANALYSER_VERSION,
        created_by=membership.user_id,
    )
    db.add(assessment)
    db.flush()

    counts = {"essential": 0, "beneficial": 0, "unnecessary": 0}
    for topic in sorted(topics, key=lambda item: item.name.casefold()):
        determination = determine_requirement(
            str(topic.id), topic.name, outcome_counts.get(topic.id, 0)
        )
        counts[determination.level] += 1
        db.add(
            VisualRequirementItem(
                assessment_id=assessment.id,
                topic_id=topic.id,
                topic_name=topic.name,
                requirement_level=VisualRequirementLevel(determination.level),
                recommended_kind=determination.recommended_kind,
                proposed_title=determination.proposed_title,
                signals=determination.signals,
                rationale=determination.rationale,
            )
        )
    assessment.essential_count = counts["essential"]
    assessment.beneficial_count = counts["beneficial"]
    assessment.unnecessary_count = counts["unnecessary"]
    record_audit_event(
        db,
        action="visual_requirements.analysed",
        resource_type="exam_blueprint_version",
        resource_id=str(version.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"essential": counts["essential"], "beneficial": counts["beneficial"]},
    )
    db.commit()
    return _assessment_response(db, workspace_id, version, assessment)


@router.get(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/visuals",
    response_model=VisualAssessmentResponse,
)
def get_visual_requirements(
    workspace_id: UUID,
    blueprint_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> VisualAssessmentResponse:
    version = _load_version(db, workspace_id, blueprint_id, version_id)
    assessment = db.scalar(
        select(VisualRequirementAssessment).where(
            VisualRequirementAssessment.blueprint_version_id == version.id
        )
    )
    return _assessment_response(db, workspace_id, version, assessment)


@router.post(
    "/workspaces/{workspace_id}/visuals/assets",
    response_model=VisualAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_visual_asset(
    workspace_id: UUID,
    payload: VisualAssetCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> VisualAssetResponse:
    """Create a visual asset as a draft version from an explicit or auto-drafted spec."""
    requirement_item: VisualRequirementItem | None = None
    if payload.requirement_item_id is not None:
        requirement_item = db.scalar(
            select(VisualRequirementItem)
            .join(
                VisualRequirementAssessment,
                VisualRequirementAssessment.id == VisualRequirementItem.assessment_id,
            )
            .where(
                VisualRequirementItem.id == payload.requirement_item_id,
                VisualRequirementAssessment.workspace_id == workspace_id,
            )
            .options(selectinload(VisualRequirementItem.assessment))
        )
        if requirement_item is None:
            raise HTTPException(status_code=404, detail="Visual requirement item not found.")

    if payload.spec is not None:
        spec = payload.spec.model_dump()
        blueprint_version_id = payload.blueprint_version_id
        if requirement_item is not None:
            blueprint_version_id = requirement_item.assessment.blueprint_version_id
    else:
        assert requirement_item is not None
        blueprint_version_id = requirement_item.assessment.blueprint_version_id
        outcomes = list(
            db.scalars(
                select(LearningOutcome.description)
                .where(LearningOutcome.topic_id == requirement_item.topic_id)
                .order_by(LearningOutcome.code)
            ).all()
        )
        kind = str(requirement_item.recommended_kind or DiagramKind.FLOWCHART)
        try:
            spec = build_auto_draft_spec(
                title=requirement_item.proposed_title,
                kind=kind,
                outcome_labels=outcomes,
            )
        except VisualSpecInvalid as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    if blueprint_version_id is None:
        raise HTTPException(
            status_code=422,
            detail="An explicit specification must reference a blueprint version or requirement item.",
        )
    version = _load_version_by_id(db, workspace_id, blueprint_version_id)

    asset, asset_version = _create_asset(db, workspace_id, version, spec, membership.user_id, requirement_item)
    record_audit_event(
        db,
        action="visual_asset.created",
        resource_type="visual_asset",
        resource_id=str(asset.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"kind": str(asset_version.diagram_kind), "blueprint_version_id": str(version.id)},
    )
    db.commit()
    return _asset_response(workspace_id, _load_asset(db, workspace_id, asset.id))


@router.post(
    "/workspaces/{workspace_id}/visuals/assets/{asset_id}/versions",
    response_model=VisualAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_visual_asset_version(
    workspace_id: UUID,
    asset_id: UUID,
    payload: VisualAssetVersionCreate,
    db: DatabaseSession,
    membership: WorkspaceEditor,
) -> VisualAssetResponse:
    """Append an immutable revision; earlier versions and decisions are preserved."""
    asset = db.scalar(
        select(VisualAsset)
        .where(VisualAsset.id == asset_id, VisualAsset.workspace_id == workspace_id)
        .with_for_update()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Visual asset not found.")
    spec = payload.spec.model_dump()
    _append_asset_version(db, asset, spec, membership.user_id)
    record_audit_event(
        db,
        action="visual_asset.version_appended",
        resource_type="visual_asset",
        resource_id=str(asset.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"version_number": asset.current_version_number},
    )
    db.commit()
    return _asset_response(workspace_id, _load_asset(db, workspace_id, asset.id))


@router.post(
    "/workspaces/{workspace_id}/visuals/assets/{asset_id}/versions/{asset_version_id}/decision",
    response_model=VisualAssetResponse,
)
def decide_visual_asset_version(
    workspace_id: UUID,
    asset_id: UUID,
    asset_version_id: UUID,
    payload: VisualDecisionRequest,
    db: DatabaseSession,
    membership: WorkspaceApprover,
) -> VisualAssetResponse:
    """Record an append-only moderator approval or rejection for one asset version."""
    asset = _load_asset(db, workspace_id, asset_id)
    asset_version = next((item for item in asset.versions if item.id == asset_version_id), None)
    if asset_version is None:
        raise HTTPException(status_code=404, detail="Visual asset version not found.")

    if payload.decision == "approved":
        report = validate_spec(dict(asset_version.spec))
        if not report["valid"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "A structurally invalid visual cannot be approved.",
                    "errors": report["errors"],
                },
            )
        asset_version.status = VisualAssetStatus.APPROVED
    else:
        asset_version.status = VisualAssetStatus.REJECTED

    db.add(
        VisualAssetDecision(
            asset_version_id=asset_version.id,
            decision=VisualDecision(payload.decision),
            rationale=payload.rationale,
            decided_by=membership.user_id,
        )
    )
    record_audit_event(
        db,
        action=f"visual_asset.{payload.decision}",
        resource_type="visual_asset_version",
        resource_id=str(asset_version.id),
        actor_user_id=membership.user_id,
        workspace_id=workspace_id,
        event_data={"asset_id": str(asset.id), "version_number": asset_version.version_number},
    )
    db.commit()
    return _asset_response(workspace_id, _load_asset(db, workspace_id, asset.id))


@router.get(
    "/workspaces/{workspace_id}/visuals/assets/{asset_id}/versions/{asset_version_id}/svg",
    responses={200: {"content": {"image/svg+xml": {}}}},
)
def get_visual_asset_svg(
    workspace_id: UUID,
    asset_id: UUID,
    asset_version_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> Response:
    """Serve the rendered, script-free SVG for review inside the authoring workspace."""
    asset_version = db.scalar(
        select(VisualAssetVersion)
        .join(VisualAsset, VisualAsset.id == VisualAssetVersion.asset_id)
        .where(
            VisualAssetVersion.id == asset_version_id,
            VisualAsset.id == asset_id,
            VisualAsset.workspace_id == workspace_id,
        )
    )
    if asset_version is None:
        raise HTTPException(status_code=404, detail="Visual asset version not found.")
    return Response(
        content=asset_version.svg_markup,
        media_type="image/svg+xml",
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/moderation",
    response_model=ModerationReportResponse,
)
def get_moderation_report(
    workspace_id: UUID,
    blueprint_id: UUID,
    version_id: UUID,
    db: DatabaseSession,
    _membership: WorkspaceEditor,
) -> ModerationReportResponse:
    """Report whether the blueprint version satisfies the publication gates."""
    version = _load_version(db, workspace_id, blueprint_id, version_id)
    report = build_moderation_report(db, version).as_dict()
    return ModerationReportResponse(blueprint_version_id=version.id, **report)


# --------------------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------------------


def func_count():
    from sqlalchemy import func

    return func.count()


def _load_version_by_id(db: Session, workspace_id: UUID, version_id: UUID) -> ExamBlueprintVersion:
    version = db.scalar(
        select(ExamBlueprintVersion)
        .join(ExamBlueprint, ExamBlueprint.id == ExamBlueprintVersion.blueprint_id)
        .where(
            ExamBlueprint.workspace_id == workspace_id,
            ExamBlueprintVersion.id == version_id,
        )
        .options(selectinload(ExamBlueprintVersion.blueprint))
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Examination blueprint version not found.")
    return version


def _create_asset(
    db: Session,
    workspace_id: UUID,
    version: ExamBlueprintVersion,
    spec: dict,
    actor_user_id: UUID,
    requirement_item: VisualRequirementItem | None,
) -> tuple[VisualAsset, VisualAssetVersion]:
    import hashlib

    report = validate_spec(spec)
    if not report["valid"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "The diagram specification is invalid.", "errors": report["errors"]},
        )
    svg = render_svg(spec)
    fingerprint = hashlib.sha256(
        f"{version.id}:{spec['kind']}:{spec['title']}".encode()
    ).hexdigest()
    existing = db.scalar(
        select(VisualAsset).where(
            VisualAsset.blueprint_version_id == version.id,
            VisualAsset.fingerprint == fingerprint,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="An equivalent visual asset already exists for this blueprint version.",
        )
    asset = VisualAsset(
        workspace_id=workspace_id,
        subject_id=version.subject_id,
        blueprint_version_id=version.id,
        requirement_item_id=requirement_item.id if requirement_item else None,
        title=str(spec["title"]),
        fingerprint=fingerprint,
        current_version_number=0,
        created_by=actor_user_id,
    )
    db.add(asset)
    db.flush()
    asset_version = _append_asset_version(db, asset, spec, actor_user_id, svg=svg, report=report)
    return asset, asset_version


def _append_asset_version(
    db: Session,
    asset: VisualAsset,
    spec: dict,
    actor_user_id: UUID,
    *,
    svg: str | None = None,
    report: dict | None = None,
) -> VisualAssetVersion:
    report = report or validate_spec(spec)
    if not report["valid"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "The diagram specification is invalid.", "errors": report["errors"]},
        )
    svg = svg or render_svg(spec)
    asset.current_version_number += 1
    asset_version = VisualAssetVersion(
        asset_id=asset.id,
        version_number=asset.current_version_number,
        diagram_kind=spec["kind"],
        spec=spec,
        svg_markup=svg,
        validation_report=report,
        alt_text=build_alt_text(spec),
        status=VisualAssetStatus.DRAFT,
        created_by=actor_user_id,
    )
    db.add(asset_version)
    db.flush()
    return asset_version


def _assessment_response(
    db: Session,
    workspace_id: UUID,
    version: ExamBlueprintVersion,
    assessment: VisualRequirementAssessment | None,
) -> VisualAssessmentResponse:
    approved = _approved_asset_version_ids(db, version.id)
    assets = list(
        db.scalars(
            select(VisualAsset)
            .where(VisualAsset.blueprint_version_id == version.id)
            .options(selectinload(VisualAsset.versions))
            .order_by(VisualAsset.created_at)
        ).all()
    )
    items: list[VisualRequirementItemResponse] = []
    if assessment is not None:
        items = [
            VisualRequirementItemResponse(
                id=item.id,
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                requirement_level=str(item.requirement_level),
                recommended_kind=str(item.recommended_kind) if item.recommended_kind else None,
                proposed_title=item.proposed_title,
                rationale=item.rationale,
                signals=item.signals,
                approved_asset_version_id=approved.get(item.id),
            )
            for item in assessment.items
        ]
    return VisualAssessmentResponse(
        id=assessment.id if assessment else None,
        blueprint_version_id=version.id,
        analyser_version=assessment.analyser_version if assessment else None,
        essential_count=assessment.essential_count if assessment else 0,
        beneficial_count=assessment.beneficial_count if assessment else 0,
        unnecessary_count=assessment.unnecessary_count if assessment else 0,
        created_at=assessment.created_at if assessment else None,
        items=items,
        assets=[_asset_response(workspace_id, asset) for asset in assets],
    )
