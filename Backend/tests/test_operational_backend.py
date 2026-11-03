"""Dashboard, notifications, facility and user-administration tests."""
from uuid import uuid4

from app.auth.security import create_access_token


def auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_dashboard_summary_is_live_and_facility_scoped(client):
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["facility_count"] == 1
    assert data["patient_count"] == 2
    assert data["active_patient_count"] == 2
    assert data["encounters_in_progress"] == 0
    assert data["notes_awaiting_review"] == 0
    assert data["lab_reports_awaiting_review"] == 0
    assert data["follow_ups_open"] == 0
    assert data["follow_ups_overdue"] == 0
    assert isinstance(data["recent_activity"], list)


def test_dashboard_for_receptionist_only_returns_patient_metrics(client):
    response = client.get(
        "/api/v1/dashboard/summary",
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["patient_count"] == 2
    assert data["active_patient_count"] == 2
    assert data["encounters_in_progress"] == 0
    assert data["notes_awaiting_review"] == 0
    assert data["lab_reports_awaiting_review"] == 0
    assert data["follow_ups_open"] == 0


def test_dashboard_requires_authenticated_role(client):
    response = client.get("/api/v1/dashboard/summary", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_lab_report_creation_creates_facility_scoped_notifications(client):
    payload = {
        "patient_id": "DEMO-0001",
        "source_system": "TEST-LIS",
        "observations": [{
            "test_code": "HB", "test_name": "Haemoglobin", "value_numeric": 13.1,
            "unit": "g/dL", "reference_range": "12-16",
        }],
    }
    created = client.post("/api/v1/lab-results", json=payload, headers=auth("TEST-LAB-WORKER"))
    assert created.status_code == 201
    report_id = created.json()["report_id"]

    clinician_inbox = client.get("/api/v1/notifications", headers=auth("TEST-CLINICIAN"))
    assert clinician_inbox.status_code == 200
    data = clinician_inbox.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1
    item = data["items"][0]
    assert item["title"] == "New laboratory report received"
    assert item["resource_type"] == "lab_reports"
    assert item["resource_id"] == report_id
    assert "Demo Patient" not in item["message"]

    other_user_inbox = client.get("/api/v1/notifications", headers=auth("TEST-RECEPTIONIST"))
    assert other_user_inbox.status_code == 200
    assert other_user_inbox.json()["total"] == 0


def test_notification_can_only_be_marked_read_by_recipient(client):
    payload = {
        "patient_id": "DEMO-0001",
        "source_system": "TEST-LIS",
        "observations": [{"test_code": "HB", "test_name": "Haemoglobin", "value_numeric": 12.5}],
    }
    created = client.post("/api/v1/lab-results", json=payload, headers=auth("TEST-LAB-WORKER"))
    assert created.status_code == 201
    inbox = client.get("/api/v1/notifications", headers=auth("TEST-CLINICIAN")).json()
    notification_id = inbox["items"][0]["notification_id"]

    forbidden = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=auth("TEST-NURSE"),
    )
    assert forbidden.status_code == 404

    marked = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=auth("TEST-CLINICIAN"),
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None
    unread = client.get(
        "/api/v1/notifications?unread_only=true",
        headers=auth("TEST-CLINICIAN"),
    )
    assert unread.status_code == 200
    assert unread.json()["total"] == 0
    assert unread.json()["unread_count"] == 0


def test_facility_admin_sees_only_users_in_managed_facility(client):
    response = client.get(
        "/api/v1/admin/users",
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()}
    assert "test_receptionist" in usernames
    assert "test_other_facility_admin" not in usernames

    outside = client.get(
        "/api/v1/admin/users?facility_id=DEMO-FACILITY-002",
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert outside.status_code == 404


def test_facility_admin_can_create_non_privileged_staff_user(client):
    response = client.post(
        "/api/v1/admin/users",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={
            "username": "new_receptionist",
            "display_name": "New Receptionist",
            "initial_password": "A-Long-Development-Password-1",
            "facility_id": "DEMO-FACILITY-001",
            "role": "receptionist",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "new_receptionist"
    assert data["is_active"] is True
    assert data["assignments"][0]["role"] == "receptionist"
    assert "password" not in data
    assert "password_hash" not in data


def test_facility_admin_cannot_grant_privileged_roles(client):
    response = client.post(
        "/api/v1/admin/users",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={
            "username": "would_be_admin",
            "display_name": "Would Be Admin",
            "initial_password": "A-Long-Development-Password-1",
            "facility_id": "DEMO-FACILITY-001",
            "role": "platform_admin",
        },
    )
    assert response.status_code == 403


def test_clinician_cannot_use_user_administration(client):
    response = client.get("/api/v1/admin/users", headers=auth("TEST-CLINICIAN"))
    assert response.status_code == 403


def test_platform_admin_can_create_and_update_facilities(client):
    created = client.post(
        "/api/v1/facilities",
        json={
            "facility_id": "DEMO-FACILITY-003",
            "name": "Demo Clinic Three",
            "district": "South-East",
            "contact_email": "admin@example.test",
        },
    )
    assert created.status_code == 201
    assert created.json()["facility_id"] == "DEMO-FACILITY-003"

    updated = client.patch(
        "/api/v1/facilities/DEMO-FACILITY-003",
        json={"district": "Gaborone"},
    )
    assert updated.status_code == 200
    assert updated.json()["district"] == "Gaborone"


def test_facility_admin_cannot_create_facilities(client):
    response = client.post(
        "/api/v1/facilities",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={"facility_id": "BLOCKED-FACILITY", "name": "Blocked Facility"},
    )
    assert response.status_code == 403


def test_facility_admin_can_assign_staff_role_only_within_own_facility(client):
    created = client.post(
        "/api/v1/admin/users",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={
            "username": "role_target",
            "display_name": "Role Target",
            "initial_password": "A-Long-Development-Password-1",
            "facility_id": "DEMO-FACILITY-001",
            "role": "receptionist",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]

    added = client.post(
        f"/api/v1/admin/users/{user_id}/assignments",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={"facility_id": "DEMO-FACILITY-001", "role": "nurse"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "nurse"

    outside = client.post(
        f"/api/v1/admin/users/{user_id}/assignments",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={"facility_id": "DEMO-FACILITY-002", "role": "nurse"},
    )
    assert outside.status_code == 404


def test_only_platform_admin_can_change_global_user_active_state(client):
    user_list = client.get("/api/v1/admin/users", headers=auth("TEST-PLATFORM-ADMIN"))
    assert user_list.status_code == 200
    receptionist = next(item for item in user_list.json() if item["username"] == "test_receptionist")

    denied = client.patch(
        f"/api/v1/admin/users/{receptionist['user_id']}",
        headers=auth("TEST-FACILITY-ADMIN"),
        json={"is_active": False},
    )
    assert denied.status_code == 403

    updated = client.patch(
        f"/api/v1/admin/users/{receptionist['user_id']}",
        headers=auth("TEST-PLATFORM-ADMIN"),
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_cannot_deactivate_last_platform_admin(client):
    response = client.get("/api/v1/admin/users", headers=auth("TEST-PLATFORM-ADMIN"))
    admin = next(item for item in response.json() if item["username"] == "test_admin")
    updated = client.patch(
        f"/api/v1/admin/users/{admin['user_id']}",
        headers=auth("TEST-PLATFORM-ADMIN"),
        json={"is_active": False},
    )
    assert updated.status_code == 409


def test_dashboard_reflects_live_workflow_records(client):
    encounter = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-0001",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Test Clinician",
            "encounter_type": "consultation",
        },
    )
    assert encounter.status_code == 201
    encounter_id = encounter.json()["encounter_id"]

    note = client.post(
        f"/api/v1/encounters/{encounter_id}/notes",
        json={"author_name": "Test Clinician", "presenting_complaint": "Synthetic test complaint"},
    )
    assert note.status_code == 201
    note_id = note.json()["note_id"]
    submitted = client.post(f"/api/v1/notes/{note_id}/submit-for-review")
    assert submitted.status_code == 200

    report = client.post(
        "/api/v1/lab-results",
        json={
            "patient_id": "DEMO-0001",
            "source_system": "TEST-LIS",
            "observations": [{"test_code": "HB", "test_name": "Haemoglobin", "value_numeric": 13.2}],
        },
    )
    assert report.status_code == 201
    report_id = report.json()["report_id"]
    assert client.patch(f"/api/v1/lab-results/{report_id}/status", json={"status": "validated"}).status_code == 200
    awaiting = client.patch(f"/api/v1/lab-results/{report_id}/status", json={"status": "awaiting_review"})
    assert awaiting.status_code == 200

    task = client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": "DEMO-0001",
            "description": "Synthetic operational follow-up",
            "due_at": "2020-01-01T00:00:00Z",
        },
    )
    assert task.status_code == 201

    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["encounters_in_progress"] == 1
    assert summary["notes_awaiting_review"] == 1
    assert summary["lab_reports_awaiting_review"] == 1
    assert summary["follow_ups_open"] == 1
    assert summary["follow_ups_overdue"] == 1
    assert len(summary["recent_activity"]) >= 4


def test_note_submission_creates_review_notification(client):
    encounter = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-0001",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Test Clinician",
            "encounter_type": "consultation",
        },
    )
    encounter_id = encounter.json()["encounter_id"]
    note = client.post(
        f"/api/v1/encounters/{encounter_id}/notes",
        json={"author_name": "Test Clinician", "presenting_complaint": "Synthetic complaint"},
    )
    note_id = note.json()["note_id"]
    submitted = client.post(
        f"/api/v1/notes/{note_id}/submit-for-review",
        headers=auth("TEST-CLINICIAN"),
    )
    assert submitted.status_code == 200
    admin_inbox = client.get("/api/v1/notifications", headers=auth("TEST-FACILITY-ADMIN"))
    assert admin_inbox.status_code == 200
    assert any(item["resource_id"] == note_id for item in admin_inbox.json()["items"])


def test_platform_admin_can_view_all_facilities_but_facility_admin_is_scoped(client):
    platform = client.get("/api/v1/facilities", headers=auth("TEST-PLATFORM-ADMIN"))
    assert platform.status_code == 200
    assert {item["facility_id"] for item in platform.json()} == {
        "DEMO-FACILITY-001", "DEMO-FACILITY-002"
    }

    facility_admin = client.get("/api/v1/facilities", headers=auth("TEST-FACILITY-ADMIN"))
    assert facility_admin.status_code == 200
    assert {item["facility_id"] for item in facility_admin.json()} == {"DEMO-FACILITY-001"}


def test_mark_all_notifications_read_only_affects_current_user(client):
    payload = {
        "patient_id": "DEMO-0001",
        "source_system": "TEST-LIS",
        "observations": [{"test_code": "HB", "test_name": "Haemoglobin", "value_numeric": 13.0}],
    }
    created = client.post("/api/v1/lab-results", json=payload, headers=auth("TEST-LAB-WORKER"))
    assert created.status_code == 201

    marked = client.post("/api/v1/notifications/read-all", headers=auth("TEST-CLINICIAN"))
    assert marked.status_code == 200
    assert marked.json() == {"updated": 1}

    other = client.get("/api/v1/notifications", headers=auth("TEST-NURSE"))
    assert other.status_code == 200
    assert other.json()["unread_count"] == 1
