"""Subject workspace ingestion: upload, extraction, classification, sufficiency.

Everything in this module operates on a single ``workspace_id``. No query in the
platform joins content across workspaces, which is what enforces subject
isolation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AcademicDocument,
    AuditLog,
    CoverageLevel,
    DocumentStatus,
    Examination,
    ExtractedContent,
    LearningOutcome,
    ProcessingStatus,
    ResourceSufficiencyReport,
    SourceReference,
    SubjectWorkspace,
    Subtopic,
    Topic,
    VisualAsset,
    VisualRequirement,
    VisualStatus,
)
from . import classification, extraction, textutil, visuals


def audit(db: Session, workspace_id: str | None, user_id: str | None, action: str,
          entity_type: str = "", entity_id: str = "", detail: dict | None = None) -> None:
    db.add(AuditLog(workspace_id=workspace_id, user_id=user_id, action=action,
                    entity_type=entity_type, entity_id=entity_id, detail=detail or {}))


def _stored_name(workspace_id: str, filename: str) -> str:
    safe = Path(filename).name.replace("..", "_")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in " ._-()")
    return f"{workspace_id}_{safe}"


def store_upload(db: Session, workspace: SubjectWorkspace, filename: str,
                 content: bytes, content_type: str = "",
                 declared_kind: str | None = None) -> AcademicDocument:
    """Persist an uploaded file and register a versioned document record."""
    settings = get_settings()
    if not extraction.is_supported(filename):
        raise ValueError(f"Unsupported file type: {Path(filename).suffix or 'unknown'}")
    if len(content) > settings.max_upload_bytes:
        raise ValueError(
            f"File exceeds the {settings.max_upload_mb} MB upload limit.")

    digest = hashlib.sha256(content).hexdigest()
    target = settings.data_dir / "uploads" / _stored_name(workspace.id, filename)
    if target.exists():
        target = target.with_name(f"{target.stem}_{digest[:8]}{target.suffix}")
    target.write_bytes(content)

    previous = db.scalars(select(AcademicDocument).where(
        AcademicDocument.workspace_id == workspace.id,
        AcademicDocument.filename == filename,
        AcademicDocument.is_latest.is_(True))).first()

    version = 1
    supersedes_id = None
    if previous is not None:
        version = previous.version + 1
        supersedes_id = previous.id
        previous.is_latest = False

    # An explicit kind from the caller (CLI flag or API field) wins; otherwise
    # infer it from the filename and content type.
    kind = declared_kind or classification.classify_document_kind(filename, content_type)
    duplicate = db.scalars(select(AcademicDocument).where(
        AcademicDocument.workspace_id == workspace.id,
        AcademicDocument.sha256 == digest)).first()

    document = AcademicDocument(
        workspace_id=workspace.id,
        filename=filename,
        stored_path=str(target),
        content_type=content_type or "",
        size_bytes=len(content),
        sha256=digest,
        version=version,
        kind=kind,
        supersedes_id=supersedes_id,
        is_latest=True,
        status=DocumentStatus.UPLOADED.value,
        processing_status=ProcessingStatus.PENDING.value,
    )
    if duplicate is not None:
        document.processing_notes = (
            f"Identical content already uploaded as document {duplicate.id[:8]} "
            f"(v{duplicate.version}). Stored for version history; duplicate detected.")
    db.add(document)
    db.flush()
    audit(db, workspace.id, workspace.owner_id, "document.upload", "document", document.id,
          {"filename": filename, "version": version, "sha256": digest[:12]})
    return document


def process_document(db: Session, document: AcademicDocument) -> AcademicDocument:
    """Extract content, record chunks and provenance, and mark processing status."""
    document.status = DocumentStatus.PROCESSING.value
    db.flush()
    result = extraction.extract(Path(document.stored_path))
    for chunk in result.chunks:
        db.add(ExtractedContent(
            document_id=document.id,
            workspace_id=document.workspace_id,
            ordinal=len(document.chunks) if document.chunks else 0,
            heading=chunk.heading[:512],
            kind=chunk.kind,
            text=chunk.text,
            page=chunk.page,
            provenance=document.kind if document.kind != "coursework"
            else "coursework",
            meta=chunk.meta or {},
        ))
    document.page_count = result.page_count
    document.extracted_chars = result.total_chars
    document.processing_status = {
        "ok": ProcessingStatus.OK.value,
        "warning": ProcessingStatus.WARNING.value,
        "error": ProcessingStatus.ERROR.value,
    }.get(result.status, ProcessingStatus.WARNING.value)
    notes = [result.notes] if result.notes else []
    if document.processing_notes:
        notes.insert(0, document.processing_notes)
    if not result.chunks:
        notes.append("No extractable text was found in this document.")
    document.processing_notes = " ".join(n for n in notes if n)
    document.status = (DocumentStatus.EXTRACTED.value
                       if result.status != "error" else DocumentStatus.FAILED.value)
    db.flush()
    audit(db, document.workspace_id, None, "document.processed", "document", document.id,
          {"chunks": len(result.chunks), "status": result.status})
    return document


def _contents(db: Session, workspace_id: str) -> list[ExtractedContent]:
    return list(db.scalars(select(ExtractedContent).where(
        ExtractedContent.workspace_id == workspace_id).order_by(ExtractedContent.ordinal)))


def _latest_documents(db: Session, workspace_id: str) -> list[AcademicDocument]:
    return list(db.scalars(select(AcademicDocument).where(
        AcademicDocument.workspace_id == workspace_id,
        AcademicDocument.is_latest.is_(True))))


def reclassify(db: Session, workspace: SubjectWorkspace) -> ResourceSufficiencyReport:
    """Rebuild topics/outcomes for the workspace and produce a sufficiency report."""
    documents = _latest_documents(db, workspace.id)
    contents = _contents(db, workspace.id)
    result = classification.classify(workspace.id, documents, contents)

    # Replace the derived hierarchy; generated examinations keep their own
    # immutable snapshots and are therefore unaffected.
    existing = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace.id)))
    preserved = {
        (t.derived_name or t.name): (t.name, t.needs_visual, t.reviewed_by_student)
        for t in existing
    }
    for topic in existing:
        db.delete(topic)
    db.flush()

    document_by_content = {c.id: c.document_id for c in contents}
    for draft in result.topics:
        prior_name, prior_visual, reviewed = preserved.get(
            draft.name, (draft.name, draft.needs_visual, False))
        topic = Topic(
            workspace_id=workspace.id,
            name=prior_name if reviewed else draft.name,
            derived_name=draft.name,
            summary=draft.summary,
            coverage=draft.coverage,
            coverage_notes=draft.coverage_notes,
            needs_visual=prior_visual if reviewed else draft.needs_visual,
            visual_rationale=draft.visual_rationale,
            keywords=draft.keywords,
            confidence=draft.confidence,
            reviewed_by_student=reviewed,
        )
        db.add(topic)
        db.flush()
        for sub_draft in draft.subtopics:
            subtopic = Subtopic(
                topic_id=topic.id, workspace_id=workspace.id, name=sub_draft.name,
                summary=sub_draft.summary, coverage=sub_draft.coverage)
            db.add(subtopic)
            db.flush()
            for outcome_draft in sub_draft.outcomes:
                outcome = LearningOutcome(
                    subtopic_id=subtopic.id, topic_id=topic.id, workspace_id=workspace.id,
                    statement=outcome_draft.statement, bloom=outcome_draft.bloom,
                    covered=True)
                db.add(outcome)
                db.flush()
                if outcome_draft.evidence:
                    db.add(SourceReference(
                        workspace_id=workspace.id, entity_type="learning_outcome",
                        entity_id=outcome.id,
                        document_id=document_by_content.get(outcome_draft.evidence),
                        content_id=outcome_draft.evidence,
                        locator=f"topic:{topic.name}",
                        quote=outcome_draft.statement[:400],
                        provenance="coursework"))
        for content_id in draft.content_ids:
            db.add(SourceReference(
                workspace_id=workspace.id, entity_type="topic", entity_id=topic.id,
                document_id=document_by_content.get(content_id), content_id=content_id,
                locator=f"topic:{topic.name}", quote="", provenance="coursework"))

    sufficiency = classification.assess_sufficiency(
        workspace.id, documents, contents, result)
    report = ResourceSufficiencyReport(
        workspace_id=workspace.id,
        adequate=sufficiency["adequate"],
        partial=sufficiency["partial"],
        missing=sufficiency["missing"],
        missing_outcomes=sufficiency["missing_outcomes"],
        conflicts=sufficiency["conflicts"],
        insufficient_types=sufficiency["insufficient_types"],
        clarifications=sufficiency["clarifications"],
        document_count=sufficiency["document_count"],
        total_chars=sufficiency["total_chars"],
        verdict=sufficiency["verdict"],
    )
    db.add(report)
    db.flush()
    audit(db, workspace.id, workspace.owner_id, "workspace.reclassified", "workspace",
          workspace.id, {"topics": len(result.topics), "verdict": sufficiency["verdict"]})
    return report


def propose_visuals(db: Session, workspace: SubjectWorkspace) -> list[VisualAsset]:
    """Stage 1-3: analyse visual requirements and construct proposed assets."""
    topics = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace.id)))
    created: list[VisualAsset] = []
    for topic in topics:
        if topic.needs_visual == VisualRequirement.UNNECESSARY.value:
            continue
        diagram_type = textutil.detect_diagram_type(
            topic.summary + " " + " ".join(topic.keywords)) or "annotated"
        key = f"{topic.id[:8]}-{diagram_type}"
        existing = db.scalars(select(VisualAsset).where(
            VisualAsset.workspace_id == workspace.id, VisualAsset.key == key,
            VisualAsset.status != VisualStatus.REJECTED.value)).first()
        if existing is not None:
            continue
        spec = visuals.infer_spec(
            key=key,
            title=f"{topic.name} — {visuals.TYPE_TITLES.get(diagram_type, 'Diagram')}",
            diagram_type=diagram_type,
            topic_name=topic.name,
            topic_id=topic.id,
            requirement=topic.needs_visual,
            intended_use=(
                f"Assessment of {topic.name}: diagram interpretation and labelling "
                f"of {diagram_type.replace('_', ' ')} components."),
            meta=_meta_for(topic, diagram_type),
        )
        svg = visuals.construct(spec)
        asset = VisualAsset(
            workspace_id=workspace.id,
            topic_id=topic.id,
            key=key,
            title=spec.title,
            diagram_type=diagram_type,
            requirement=topic.needs_visual,
            status=VisualStatus.PROPOSED.value,
            version=1,
            spec={
                "key": key, "title": spec.title, "diagram_type": diagram_type,
                "labels": spec.labels, "nodes": spec.nodes,
                "requirement": topic.needs_visual, "intended_use": spec.intended_use,
                "meta": spec.meta,
            },
            svg=svg,
            labels=spec.labels,
            intended_use=spec.intended_use,
            provenance="generated",
        )
        db.add(asset)
        db.flush()
        created.append(asset)
    audit(db, workspace.id, workspace.owner_id, "visuals.proposed", "workspace",
          workspace.id, {"count": len(created)})
    return created


def _meta_for(topic: Topic, diagram_type: str) -> dict:
    """Seed diagram structure from the topic's own keywords."""
    keywords = [str(k) for k in (topic.keywords or [])][:6]
    if diagram_type in {"table", "graph"}:
        return {"headers": ["Item", "Value", "Notes"],
                "rows": [[kw, "", ""] for kw in keywords[:4]] or [["", "", ""]]}
    return {}


def approve_visual(db: Session, asset: VisualAsset, approve: bool,
                   user_id: str | None) -> VisualAsset:
    """Stage 4: record the student's approval decision."""
    from datetime import datetime, timezone

    if approve:
        asset.status = VisualStatus.APPROVED.value
        asset.approved_by = user_id
        asset.approved_at = datetime.now(timezone.utc)
    else:
        asset.status = VisualStatus.REJECTED.value
        asset.approved_by = user_id
        asset.approved_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, asset.workspace_id, user_id,
          "visual.approved" if approve else "visual.rejected", "visual_asset", asset.id)
    return asset


def revise_visual(db: Session, asset: VisualAsset, *, title: str | None = None,
                  labels: list[str] | None = None) -> VisualAsset:
    """Create a new version of an asset when the student corrects it."""
    new_version = asset.version + 1
    spec = dict(asset.spec or {})
    if title:
        spec["title"] = title
    if labels is not None:
        spec["labels"] = labels
        spec["nodes"] = [{"label": label} for label in labels]
    spec_obj = visuals.VisualSpec(
        key=asset.key,
        title=spec.get("title", asset.title),
        diagram_type=asset.diagram_type,
        labels=spec.get("labels", asset.labels or []),
        nodes=spec.get("nodes", []),
        meta=spec.get("meta", {}),
    )
    asset.svg = visuals.construct(spec_obj)
    asset.spec = spec
    asset.title = spec_obj.title
    asset.labels = spec_obj.labels
    asset.version = new_version
    asset.status = VisualStatus.PROPOSED.value
    asset.approved_by = None
    asset.approved_at = None
    db.flush()
    audit(db, asset.workspace_id, None, "visual.revised", "visual_asset", asset.id,
          {"version": new_version})
    return asset


def topic_bundles(db: Session, workspace_id: str, topic_ids: list[str] | None = None) -> list[dict]:
    """Assemble the per-topic material bundles used for question generation."""
    query = select(Topic).where(Topic.workspace_id == workspace_id)
    topics = list(db.scalars(query))
    if topic_ids:
        wanted = set(topic_ids)
        topics = [t for t in topics if t.id in wanted] or topics
    contents = _contents(db, workspace_id)
    bundles: list[dict] = []
    for topic in topics:
        subtopics = list(db.scalars(select(Subtopic).where(Subtopic.topic_id == topic.id)))
        subtopic_ids = [s.id for s in subtopics]
        outcomes = list(db.scalars(select(LearningOutcome).where(
            LearningOutcome.topic_id == topic.id)))
        refs = {r.content_id for r in db.scalars(select(SourceReference).where(
            SourceReference.workspace_id == workspace_id,
            SourceReference.entity_type == "topic",
            SourceReference.entity_id == topic.id))}
        topic_contents = [c for c in contents if c.id in refs]
        if not topic_contents:
            keywords = [str(k).lower() for k in (topic.keywords or [])]
            topic_contents = [
                c for c in contents
                if any(k in c.text.lower() for k in keywords[:5])
            ][:60]
        bundles.append({
            "topic": topic,
            "contents": topic_contents,
            "subtopics": subtopics,
            "outcomes": outcomes,
            "subtopic_ids": subtopic_ids,
        })
    return bundles


def workspace_summary(db: Session, workspace: SubjectWorkspace) -> dict:
    documents = _latest_documents(db, workspace.id)
    contents = _contents(db, workspace.id)
    topics = list(db.scalars(select(Topic).where(Topic.workspace_id == workspace.id)))
    visuals_list = list(db.scalars(select(VisualAsset).where(
        VisualAsset.workspace_id == workspace.id)))
    latest_report = db.scalars(select(ResourceSufficiencyReport).where(
        ResourceSufficiencyReport.workspace_id == workspace.id
    ).order_by(ResourceSufficiencyReport.created_at.desc())).first()
    return {
        "document_count": len(documents),
        "extracted_chars": sum(len(c.text) for c in contents),
        "topic_count": len(topics),
        "outcome_count": sum(
            len(list(db.scalars(select(LearningOutcome).where(
                LearningOutcome.topic_id == t.id)))) for t in topics),
        "visual_count": len(visuals_list),
        "approved_visuals": sum(1 for v in visuals_list if v.status == VisualStatus.APPROVED.value),
        "proposed_visuals": sum(1 for v in visuals_list if v.status == VisualStatus.PROPOSED.value),
        "sufficiency_verdict": latest_report.verdict if latest_report else "",
        "examination_count": len(list(db.scalars(select(Examination).where(
            Examination.workspace_id == workspace.id)))),
    }
