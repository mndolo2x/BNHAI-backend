"""Create local synthetic demo users and print their initial passwords once.

Run after applying the latest Alembic migration:
    python -m app.seed_demo_users

This script is for local development only. It does not create production identities.
"""
from datetime import datetime, timezone
import secrets
from uuid import uuid4

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.models import FacilityRecord, UserFacilityRoleRecord, UserRecord
from app.db.session import SessionLocal

DEMO_FACILITY_ID = "DEMO-FACILITY-001"
DEMO_USERS = (
    ("receptionist_demo", "Demo Receptionist", "receptionist"),
    ("nurse_demo", "Demo Nurse", "nurse"),
    ("clinician_demo", "Demo Clinician", "clinician"),
    ("laboratory_demo", "Demo Laboratory Worker", "laboratory_worker"),
    ("followup_demo", "Demo Follow-up Worker", "follow_up_worker"),
    ("facility_admin_demo", "Demo Facility Administrator", "facility_admin"),
    ("auditor_demo", "Demo Auditor", "auditor"),
    ("platform_admin_demo", "Demo Platform Administrator", "platform_admin"),
)


def main() -> None:
    """Seed missing demo accounts without resetting any existing passwords."""
    created_credentials: list[tuple[str, str, str]] = []
    skipped: list[str] = []
    with SessionLocal() as db:
        if db.get(FacilityRecord, DEMO_FACILITY_ID) is None:
            db.add(FacilityRecord(
                facility_id=DEMO_FACILITY_ID,
                name="Demo Facility 001",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            db.flush()
        for username, display_name, role in DEMO_USERS:
            existing = db.scalar(select(UserRecord).where(UserRecord.username == username))
            if existing is not None:
                skipped.append(username)
                continue

            password = secrets.token_urlsafe(18)
            user = UserRecord(
                user_id=str(uuid4()),
                username=username,
                display_name=display_name,
                password_hash=hash_password(password),
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.flush()
            db.add(
                UserFacilityRoleRecord(
                    assignment_id=str(uuid4()),
                    user_id=user.user_id,
                    facility_id=DEMO_FACILITY_ID,
                    role=role,
                    assigned_at=datetime.now(timezone.utc),
                )
            )
            created_credentials.append((username, password, role))
        db.commit()

    if created_credentials:
        print("Created development-only users. Save these generated passwords now; they are not shown again.")
        for username, password, role in created_credentials:
            print(f"username: {username} | password: {password} | role: {role}")
    if skipped:
        print("Skipped existing users; their passwords and roles were not reset:")
        for username in skipped:
            print(f"- {username}")
    if not created_credentials and not skipped:
        print("No demo users were configured.")


if __name__ == "__main__":
    main()
