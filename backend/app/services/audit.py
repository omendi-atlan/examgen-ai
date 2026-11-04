"""Transactional audit-event recording."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    actor_user_id: UUID | None,
    workspace_id: UUID | None = None,
    resource_id: str | None = None,
    event_data: dict[str, object] | None = None,
) -> AuditEvent:
    """Add an audit event to the caller's transaction.

    Callers must never place credentials, password material, tokens, or answer keys
    in event_data. The event is committed atomically with the business operation.
    """
    event = AuditEvent(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        event_data=event_data or {},
    )
    db.add(event)
    return event
