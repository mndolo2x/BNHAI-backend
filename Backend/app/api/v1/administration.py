"""Facility directory and user/role administration for the operational backend."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.security import hash_password
from app.db.models import FacilityRecord, UserFacilityRoleRecord, UserRecord
from app.db.session import get_db
from app.models.operational import (
    FacilityCreate, FacilityRead, FacilityRoleRead, FacilityUpdate,
    ManagedUserCreate, ManagedUserRead, ManagedUserUpdate, RoleAssignmentCreate,
)

router = APIRouter(tags=["Administration"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

PRIVILEGED_ROLES = {"facility_admin", "platform_admin"}
FACILITY_ADMIN_ASSIGNABLE_ROLES = {
    "receptionist", "nurse", "clinician", "laboratory_worker", "follow_up_worker", "auditor",
}


def managed_facility_ids(db: Session, user: AuthenticatedUser) -> set[str]:
    """Platform admins manage all facilities; facility admins manage assigned sites only."""
    if "platform_admin" in user.role_names:
        return set(db.scalars(select(FacilityRecord.facility_id)).all())
    return {
        item.facility_id
        for item in user.assignments
        if item.role == "facility_admin"
    }


def _ensure_facility_manage_access(db: Session, user: AuthenticatedUser, facility_id: str) -> None:
    if facility_id not in managed_facility_ids(db, user):
        raise HTTPException(status_code=404, detail="Facility not found")


def _user_response(db: Session, user_record: UserRecord, visible_facilities: set[str]) -> ManagedUserRead:
    assignments = list(db.scalars(
        select(UserFacilityRoleRecord)
        .where(
            UserFacilityRoleRecord.user_id == user_record.user_id,
            UserFacilityRoleRecord.facility_id.in_(visible_facilities),
        )
        .order_by(UserFacilityRoleRecord.facility_id, UserFacilityRoleRecord.role)
    ).all())
    return ManagedUserRead(
        user_id=user_record.user_id,
        username=user_record.username,
        display_name=user_record.display_name,
        is_active=user_record.is_active,
        created_at=user_record.created_at,
        assignments=[FacilityRoleRead.model_validate(item) for item in assignments],
    )


def _check_assignable_role(user: AuthenticatedUser, role: str) -> None:
    if "platform_admin" not in user.role_names and role not in FACILITY_ADMIN_ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Facility administrators cannot grant facility_admin or platform_admin roles.",
        )


@router.get("/admin/users", response_model=list[ManagedUserRead], summary="List users in managed facilities")
def list_managed_users(
    db: DbSession,
    user: CurrentUser,
    facility_id: str | None = Query(default=None, min_length=2, max_length=80),
    search: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[ManagedUserRead]:
    facilities = managed_facility_ids(db, user)
    if facility_id:
        if facility_id not in facilities:
            raise HTTPException(status_code=404, detail="Facility not found")
        facilities = {facility_id}
    if not facilities:
        return []
    statement = (
        select(UserRecord)
        .join(UserFacilityRoleRecord, UserFacilityRoleRecord.user_id == UserRecord.user_id)
        .where(UserFacilityRoleRecord.facility_id.in_(facilities))
        .distinct()
        .order_by(UserRecord.username)
    )
    if search and search.strip():
        term = f"%{search.strip().casefold()}%"
        statement = statement.where(
            func.lower(UserRecord.username).like(term)
            | func.lower(UserRecord.display_name).like(term)
        )
    users = list(db.scalars(statement).all())
    return [_user_response(db, item, facilities) for item in users]


@router.post(
    "/admin/users",
    response_model=ManagedUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user and initial facility role",
)
def create_managed_user(payload: ManagedUserCreate, db: DbSession, user: CurrentUser) -> ManagedUserRead:
    _ensure_facility_manage_access(db, user, payload.facility_id)
    _check_assignable_role(user, payload.role.value)
    username = payload.username.strip().casefold()
    if db.scalar(select(UserRecord).where(func.lower(UserRecord.username) == username)) is not None:
        raise HTTPException(status_code=409, detail="A user with this username already exists")
    now = datetime.now(timezone.utc)
    record = UserRecord(
        user_id=str(uuid4()),
        username=username,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.initial_password.get_secret_value()),
        is_active=True,
        created_at=now,
    )
    assignment = UserFacilityRoleRecord(
        assignment_id=str(uuid4()),
        user_id=record.user_id,
        facility_id=payload.facility_id,
        role=payload.role.value,
        assigned_at=now,
    )
    db.add(record)
    db.flush()  # Persist the user row before inserting its role assignment (FK dependency).
    db.add(assignment)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create user; verify the username and facility.") from error
    return _user_response(db, record, {payload.facility_id})


@router.patch("/admin/users/{user_id}", response_model=ManagedUserRead, summary="Update a user account (platform administrator only)")
def update_managed_user(
    user_id: str,
    payload: ManagedUserUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ManagedUserRead:
    record = db.get(UserRecord, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    if changes.get("is_active") is False and record.is_active:
        active_platform_admins = int(db.scalar(
            select(func.count(func.distinct(UserRecord.user_id)))
            .join(UserFacilityRoleRecord, UserFacilityRoleRecord.user_id == UserRecord.user_id)
            .where(UserRecord.is_active.is_(True), UserFacilityRoleRecord.role == "platform_admin")
        ) or 0)
        record_is_platform_admin = db.scalar(select(UserFacilityRoleRecord.assignment_id).where(
            UserFacilityRoleRecord.user_id == record.user_id,
            UserFacilityRoleRecord.role == "platform_admin",
        )) is not None
        if record_is_platform_admin and active_platform_admins <= 1:
            raise HTTPException(status_code=409, detail="Cannot deactivate the last active platform administrator")
    for field, value in changes.items():
        if value is not None:
            setattr(record, field, value.strip() if field == "display_name" else value)
    db.commit()
    db.refresh(record)
    return _user_response(db, record, managed_facility_ids(db, user))


@router.post(
    "/admin/users/{user_id}/assignments",
    response_model=FacilityRoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a role to a user at a facility",
)
def add_user_assignment(
    user_id: str,
    payload: RoleAssignmentCreate,
    db: DbSession,
    user: CurrentUser,
) -> UserFacilityRoleRecord:
    _ensure_facility_manage_access(db, user, payload.facility_id)
    _check_assignable_role(user, payload.role.value)
    record = db.get(UserRecord, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.scalar(select(UserFacilityRoleRecord).where(
        UserFacilityRoleRecord.user_id == user_id,
        UserFacilityRoleRecord.facility_id == payload.facility_id,
        UserFacilityRoleRecord.role == payload.role.value,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="This role is already assigned at the selected facility")
    assignment = UserFacilityRoleRecord(
        assignment_id=str(uuid4()),
        user_id=user_id,
        facility_id=payload.facility_id,
        role=payload.role.value,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(assignment)
    try:
        db.commit()
        db.refresh(assignment)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create role assignment") from error
    return assignment


@router.delete(
    "/admin/users/{user_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a role assignment at a managed facility",
)
def remove_user_assignment(
    user_id: str,
    assignment_id: str,
    db: DbSession,
    user: CurrentUser,
) -> None:
    assignment = db.scalar(select(UserFacilityRoleRecord).where(
        UserFacilityRoleRecord.assignment_id == assignment_id,
        UserFacilityRoleRecord.user_id == user_id,
    ))
    if assignment is None:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    _ensure_facility_manage_access(db, user, assignment.facility_id)
    _check_assignable_role(user, assignment.role)
    if assignment.role == "platform_admin":
        active_admin_count = int(db.scalar(
            select(func.count(func.distinct(UserRecord.user_id)))
            .join(UserFacilityRoleRecord, UserFacilityRoleRecord.user_id == UserRecord.user_id)
            .where(UserRecord.is_active.is_(True), UserFacilityRoleRecord.role == "platform_admin")
        ) or 0)
        if active_admin_count <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last active platform administrator assignment")
    db.delete(assignment)
    db.commit()
    return None


@router.get("/facilities", response_model=list[FacilityRead], summary="List facilities visible to the administrator")
def list_facilities(db: DbSession, user: CurrentUser) -> list[FacilityRecord]:
    facilities = managed_facility_ids(db, user)
    if not facilities:
        return []
    return list(db.scalars(
        select(FacilityRecord).where(FacilityRecord.facility_id.in_(facilities))
        .order_by(FacilityRecord.name, FacilityRecord.facility_id)
    ).all())


@router.post(
    "/facilities",
    response_model=FacilityRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a facility (platform administrator only)",
)
def create_facility(payload: FacilityCreate, db: DbSession, user: CurrentUser) -> FacilityRecord:
    if db.get(FacilityRecord, payload.facility_id) is not None:
        raise HTTPException(status_code=409, detail="Facility identifier already exists")
    now = datetime.now(timezone.utc)
    record = FacilityRecord(
        facility_id=payload.facility_id.strip(),
        name=payload.name.strip(),
        district=payload.district,
        address=payload.address,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/facilities/{facility_id}", response_model=FacilityRead, summary="Update facility directory details")
def update_facility(
    facility_id: str,
    payload: FacilityUpdate,
    db: DbSession,
    user: CurrentUser,
) -> FacilityRecord:
    record = db.get(FacilityRecord, facility_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    if "name" in changes and changes["name"] is None:
        raise HTTPException(status_code=422, detail="Facility name cannot be null")
    for field, value in changes.items():
        setattr(record, field, value.strip() if value is not None else None)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record
