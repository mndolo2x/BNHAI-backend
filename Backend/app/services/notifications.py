"""Create internal operational notifications without embedding clinical details."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NotificationRecord, UserFacilityRoleRecord, UserRecord


def notify_facility_roles(
    db: Session,
    *,
    facility_id: str,
    roles: set[str],
    category: str,
    title: str,
    message: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    exclude_user_id: str | None = None,
) -> int:
    """Queue a message for active users holding one of roles at this facility.

    Notification messages intentionally contain workflow metadata only. Do not
    include patient names, diagnoses, test values, or other clinical content.
    """
    if not roles:
        return 0
    statement = (
        select(UserRecord.user_id)
        .join(UserFacilityRoleRecord, UserFacilityRoleRecord.user_id == UserRecord.user_id)
        .where(
            UserRecord.is_active.is_(True),
            UserFacilityRoleRecord.facility_id == facility_id,
            UserFacilityRoleRecord.role.in_(roles),
        )
        .distinct()
    )
    if exclude_user_id:
        statement = statement.where(UserRecord.user_id != exclude_user_id)
    recipients = list(db.scalars(statement).all())
    for user_id in recipients:
        db.add(
            NotificationRecord(
                notification_id=str(uuid4()),
                recipient_user_id=user_id,
                facility_id=facility_id,
                category=category,
                title=title,
                message=message,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
    return len(recipients)
