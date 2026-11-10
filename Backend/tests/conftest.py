"""Isolated database and API client fixtures for each test."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token, hash_password
from app.db.base import Base
from app.db import models  # noqa: F401 - registers ORM tables
from app.db.models import UserRecord, UserFacilityRoleRecord
from app.db.seed import seed_demo_patients
from app.db.session import get_db
from app.main import app

TEST_PASSWORD = "TestPassword123!"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)
TEST_USERS = (
    ("TEST-PLATFORM-ADMIN", "test_admin", "Test Administrator", "platform_admin"),
    ("TEST-CLINICIAN", "test_clinician", "Test Clinician", "clinician"),
    ("TEST-RECEPTIONIST", "test_receptionist", "Test Receptionist", "receptionist"),
    ("TEST-LAB-WORKER", "test_lab_worker", "Test Laboratory Worker", "laboratory_worker"),
    ("TEST-FOLLOWUP-WORKER", "test_followup_worker", "Test Follow-up Worker", "follow_up_worker"),
    ("TEST-AUDITOR", "test_auditor", "Test Auditor", "auditor"),
    ("TEST-FACILITY-ADMIN", "test_facility_admin", "Test Facility Administrator", "facility_admin"),
    ("TEST-OTHER-FACILITY-ADMIN", "test_other_facility_admin", "Other Facility Administrator", "facility_admin"),
    ("TEST-NURSE", "test_nurse", "Test Nurse", "nurse"),
)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def _enable_test_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Iterator[Session]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestingSessionLocal() as db:
        seed_demo_patients(db)
        for user_id, username, display_name, role in TEST_USERS:
            user = UserRecord(
                user_id=user_id,
                username=username,
                display_name=display_name,
                password_hash=TEST_PASSWORD_HASH,
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(
                UserFacilityRoleRecord(
                    assignment_id=f"ASSIGNMENT-{user_id}",
                    user_id=user_id,
                    facility_id=("DEMO-FACILITY-002" if user_id == "TEST-OTHER-FACILITY-ADMIN" else "DEMO-FACILITY-001"),
                    role=role,
                )
            )

        # Dedicated synthetic patient account.
        # No staff facility-role assignment is created.
        db.add(
            UserRecord(
                user_id="TEST-PORTAL-PATIENT",
                username="test_portal_patient",
                display_name="Test Portal Patient",
                password_hash=TEST_PASSWORD_HASH,
                is_active=True,
            )
        )
        db.commit()

    try:
        with TestClient(
            app,
            headers={"Authorization": f"Bearer {create_access_token('TEST-PLATFORM-ADMIN')}"},
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()
