"""Development audit logging for successful ORM database mutations.

This intentionally records metadata only (not clinical field values). Authenticated API requests set the actor on the request-scoped SQLAlchemy
session. Setup scripts and offline mutations still use a development placeholder.
Reads, failed requests, and denied access are not audited by this module.
"""
from uuid import uuid4

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db.models import AuditEventRecord


@event.listens_for(Session, "before_commit")
def record_successful_mutation_metadata(session: Session) -> None:
    """Add audit events for new, changed, or deleted ORM rows in this commit."""
    changes: list[tuple[object, str]] = []
    seen: set[int] = set()

    for obj in list(session.new):
        if isinstance(obj, AuditEventRecord) or id(obj) in seen:
            continue
        seen.add(id(obj))
        changes.append((obj, "created"))

    for obj in list(session.dirty):
        if isinstance(obj, AuditEventRecord) or id(obj) in seen:
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        seen.add(id(obj))
        changes.append((obj, "updated"))

    for obj in list(session.deleted):
        if isinstance(obj, AuditEventRecord) or id(obj) in seen:
            continue
        seen.add(id(obj))
        changes.append((obj, "deleted"))

    for obj, action in changes:
        state = inspect(obj)
        mapper = state.mapper
        values = []
        for column in mapper.primary_key:
            attribute_name = mapper.get_property_by_column(column).key
            value = getattr(obj, attribute_name, None)
            if value is not None:
                values.append(str(value))
        resource_id = ":".join(values) if values else None
        session.add(
            AuditEventRecord(
                event_id=str(uuid4()),
                actor_id=str(session.info.get("audit_actor_id", "DEVELOPMENT-MODE-UNVERIFIED")),
                actor_source=str(session.info.get("audit_actor_source", "development-placeholder")),
                action=action,
                resource_type=mapper.local_table.name,
                resource_id=resource_id,
                outcome="success",
            )
        )
