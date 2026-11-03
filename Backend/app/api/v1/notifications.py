"""Authenticated notification inbox for operational workflow events."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.models import NotificationRecord
from app.db.session import get_db
from app.models.operational import NotificationList, NotificationRead

router = APIRouter(prefix="/notifications", tags=["Notifications"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get("", response_model=NotificationList, summary="List the current user's notifications")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
) -> NotificationList:
    base = select(NotificationRecord).where(NotificationRecord.recipient_user_id == user.user_id)
    unread_count = int(db.scalar(
        select(func.count()).select_from(NotificationRecord).where(
            NotificationRecord.recipient_user_id == user.user_id,
            NotificationRecord.read_at.is_(None),
        )
    ) or 0)
    if unread_only:
        base = base.where(NotificationRecord.read_at.is_(None))
    rows = list(db.scalars(
        base.order_by(NotificationRecord.created_at.desc(), NotificationRecord.notification_id.desc()).limit(limit)
    ).all())
    total = int(db.scalar(
        select(func.count()).select_from(NotificationRecord).where(
            NotificationRecord.recipient_user_id == user.user_id,
            *( [NotificationRecord.read_at.is_(None)] if unread_only else [] ),
        )
    ) or 0)
    return NotificationList(items=rows, total=total, unread_count=unread_count)


@router.patch("/{notification_id}/read", response_model=NotificationRead, summary="Mark one notification as read")
def mark_notification_read(notification_id: str, db: DbSession, user: CurrentUser) -> NotificationRecord:
    notification = db.scalar(select(NotificationRecord).where(
        NotificationRecord.notification_id == notification_id,
        NotificationRecord.recipient_user_id == user.user_id,
    ))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all", summary="Mark all of the current user's notifications as read")
def mark_all_notifications_read(db: DbSession, user: CurrentUser) -> dict[str, int]:
    notifications = list(db.scalars(select(NotificationRecord).where(
        NotificationRecord.recipient_user_id == user.user_id,
        NotificationRecord.read_at.is_(None),
    )).all())
    now = datetime.now(timezone.utc)
    for notification in notifications:
        notification.read_at = now
    if notifications:
        db.commit()
    return {"updated": len(notifications)}
