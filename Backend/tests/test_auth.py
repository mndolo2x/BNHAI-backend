"""Tests for login, bearer authentication, and endpoint role permissions."""
from fastapi.testclient import TestClient

from app.auth.security import create_access_token

TEST_PASSWORD = "TestPassword123!"


def auth_header(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_login_returns_short_lived_access_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "test_clinician", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    assert body["access_token"]

    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["username"] == "test_clinician"
    assert {item["role"] for item in profile.json()["assignments"]} == {"clinician"}


def test_login_rejects_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "test_clinician", "password": "wrong password"},
    )
    assert response.status_code == 401


def test_login_rejects_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "not-a-user", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401


def test_protected_patient_api_rejects_invalid_bearer_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/patients",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401


def test_current_user_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": ""})
    assert response.status_code == 401


def test_receptionist_can_read_patients_but_cannot_create_encounter(client: TestClient) -> None:
    headers = auth_header("TEST-RECEPTIONIST")
    read_response = client.get("/api/v1/patients", headers=headers)
    assert read_response.status_code == 200

    write_response = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={
            "patient_id": "DEMO-0001",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Test Receptionist",
            "encounter_type": "consultation",
        },
    )
    assert write_response.status_code == 403


def test_lab_worker_cannot_read_audit_log(client: TestClient) -> None:
    response = client.get("/api/v1/audit-events", headers=auth_header("TEST-LAB-WORKER"))
    assert response.status_code == 403


def test_auditor_can_read_audit_log_but_cannot_create_patient(client: TestClient) -> None:
    headers = auth_header("TEST-AUDITOR")
    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert audit_response.status_code == 200

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "patient_id": "DEMO-AUDITOR-DENIED",
            "display_name": "Synthetic Test Patient",
            "facility_id": "DEMO-FACILITY-001",
        },
    )
    assert patient_response.status_code == 403


def test_inactive_user_token_is_rejected(client: TestClient) -> None:
    # Temporarily disable the clinician in the fixture's isolated database.
    from app.db.models import UserRecord
    from app.db.session import get_db

    override = client.app.dependency_overrides[get_db]
    generator = override()
    db = next(generator)
    try:
        user = db.get(UserRecord, "TEST-CLINICIAN")
        assert user is not None
        user.is_active = False
        db.commit()
    finally:
        try:
            next(generator)
        except StopIteration:
            pass

    response = client.get("/api/v1/patients", headers=auth_header("TEST-CLINICIAN"))
    assert response.status_code == 401


def test_unknown_api_policy_is_denied(client: TestClient) -> None:
    from app.auth.dependencies import required_roles_for_request

    assert required_roles_for_request("GET", "/api/v1/unknown-resource") is None


def test_revoked_facility_admin_role_takes_effect_immediately(client: TestClient) -> None:
    """An existing token must not retain permissions after role removal."""
    from app.db.models import UserFacilityRoleRecord
    from app.db.session import get_db

    headers = auth_header("TEST-FACILITY-ADMIN")

    before = client.get("/api/v1/patients", headers=headers)
    assert before.status_code == 200, before.text

    override = client.app.dependency_overrides[get_db]
    generator = override()
    db = next(generator)

    try:
        assignment = db.get(
            UserFacilityRoleRecord,
            "ASSIGNMENT-TEST-FACILITY-ADMIN",
        )
        assert assignment is not None
        assert assignment.role == "facility_admin"

        db.delete(assignment)
        db.commit()
    finally:
        try:
            next(generator)
        except StopIteration:
            pass

    profile = client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["assignments"] == []

    after = client.get("/api/v1/patients", headers=headers)
    assert after.status_code == 403, after.text


def test_expired_access_token_is_rejected(client: TestClient) -> None:
    """Expired access tokens must not authenticate users."""
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.auth.security import JWT_SECRET_KEY, ALGORITHM

    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "TEST-CLINICIAN",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "type": "access",
        },
        JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401, response.text


def test_missing_expiration_claim_is_rejected(client: TestClient) -> None:
    """Tokens without the required expiration claim must be rejected."""
    from datetime import datetime, timezone
    import jwt
    from app.auth.security import JWT_SECRET_KEY, ALGORITHM

    token = jwt.encode(
        {
            "sub": "TEST-CLINICIAN",
            "iat": datetime.now(timezone.utc),
            "type": "access",
        },
        JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401, response.text
