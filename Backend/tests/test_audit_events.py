"""Tests for development audit metadata on successful database mutations."""
from datetime import datetime, timezone


def create_patient(client, patient_id="DEMO-AUDIT-0001"):
    response = client.post(
        "/api/v1/patients",
        json={
            "patient_id": patient_id,
            "display_name": "Synthetic Audit Patient",
            "date_of_birth": "2000-01-01",
            "record_status": "active",
            "facility_id": "DEMO-FACILITY-001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_patient_creation_is_audited_without_record_content(client):
    patient = create_patient(client)

    response = client.get(
        "/api/v1/audit-events",
        params={
            "action": "created",
            "resource_type": "patients",
            "resource_id": patient["patient_id"],
        },
    )

    assert response.status_code == 200, response.text
    events = response.json()
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "created"
    assert event["resource_type"] == "patients"
    assert event["resource_id"] == patient["patient_id"]
    assert event["outcome"] == "success"
    assert event["actor_id"] == "TEST-PLATFORM-ADMIN"
    assert "Synthetic Audit Patient" not in str(event)


def test_followup_status_update_is_audited(client):
    patient = create_patient(client, "DEMO-AUDIT-0002")
    create_response = client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": patient["patient_id"],
            "description": "Synthetic audit task",
            "assigned_to": "Demo Worker",
        },
    )
    assert create_response.status_code == 201, create_response.text
    task_id = create_response.json()["task_id"]

    update_response = client.patch(
        f"/api/v1/follow-ups/{task_id}",
        json={"status": "in_progress"},
    )
    assert update_response.status_code == 200, update_response.text

    response = client.get(
        "/api/v1/audit-events",
        params={
            "action": "updated",
            "resource_type": "follow_up_tasks",
            "resource_id": task_id,
        },
    )
    assert response.status_code == 200, response.text
    events = response.json()
    assert len(events) == 1
    assert events[0]["resource_id"] == task_id
    assert events[0]["action"] == "updated"


def test_audit_events_can_be_filtered_and_limited(client):
    first = create_patient(client, "DEMO-AUDIT-0003")
    second = create_patient(client, "DEMO-AUDIT-0004")

    response = client.get(
        "/api/v1/audit-events",
        params={"resource_type": "patients", "limit": 1},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1

    response = client.get(
        "/api/v1/audit-events",
        params={"resource_type": "patients", "resource_id": first["patient_id"]},
    )
    assert response.status_code == 200, response.text
    assert all(item["resource_id"] == first["patient_id"] for item in response.json())


def test_audit_endpoint_rejects_invalid_action_filter(client):
    response = client.get("/api/v1/audit-events", params={"action": "approved"})
    assert response.status_code == 422


def test_audit_events_are_ordered_newest_first(client):
    create_patient(client, "DEMO-AUDIT-0005")
    create_patient(client, "DEMO-AUDIT-0006")
    response = client.get("/api/v1/audit-events", params={"resource_type": "patients", "limit": 10})
    assert response.status_code == 200, response.text
    events = response.json()
    assert len(events) >= 2
    occurred = [datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00")) for item in events]
    assert occurred == sorted(occurred, reverse=True)


def test_successful_workspace_read_appears_in_scoped_audit_api(client):
    """Audit readers can filter successful patient workspace reads."""
    workspace = client.get("/api/v1/patients/DEMO-0001/workspace")
    assert workspace.status_code == 200, workspace.text

    response = client.get(
        "/api/v1/audit-events",
        params={
            "action": "read",
            "resource_type": "patients",
            "resource_id": "DEMO-0001",
        },
    )
    assert response.status_code == 200, response.text
    events = response.json()
    assert len(events) == 1
    assert events[0]["actor_id"] == "TEST-PLATFORM-ADMIN"
    assert events[0]["action"] == "read"
    assert events[0]["outcome"] == "success"
    assert "clinical_notes" not in response.text


def test_denied_workspace_read_is_visible_only_to_patient_facility(client):
    """Denied reads are visible to authorized audit readers at that facility only."""
    from app.auth.security import create_access_token

    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    denial = client.get(
        "/api/v1/patients/DEMO-0001/workspace",
        headers=receptionist_headers,
    )
    assert denial.status_code == 403, denial.text

    params = {
        "action": "read",
        "resource_type": "patients",
        "resource_id": "DEMO-0001",
    }
    own_facility = client.get("/api/v1/audit-events", params=params)
    assert own_facility.status_code == 200, own_facility.text
    own_events = own_facility.json()
    assert len(own_events) == 1, own_events
    assert own_events[0]["actor_id"] == "TEST-RECEPTIONIST"
    assert own_events[0]["action"] == "read"
    assert own_events[0]["outcome"] == "denied"

    other_facility_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-OTHER-FACILITY-ADMIN')}"
    }
    other_facility = client.get(
        "/api/v1/audit-events",
        params=params,
        headers=other_facility_headers,
    )
    assert other_facility.status_code == 200, other_facility.text
    assert other_facility.json() == []


def test_non_audit_roles_cannot_list_patient_access_events(client):
    """Non-auditor staff cannot retrieve patient access metadata."""
    from app.auth.security import create_access_token

    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    denied_read = client.get(
        "/api/v1/patients/DEMO-0001/workspace",
        headers=receptionist_headers,
    )
    assert denied_read.status_code == 403, denied_read.text

    for user_id in ("TEST-RECEPTIONIST", "TEST-CLINICIAN"):
        headers = {
            "Authorization": f"Bearer {create_access_token(user_id)}"
        }
        response = client.get(
            "/api/v1/audit-events",
            params={
                "action": "read",
                "resource_type": "patients",
                "resource_id": "DEMO-0001",
            },
            headers=headers,
        )
        assert response.status_code == 403, (
            user_id, response.status_code, response.text
        )
        assert "TEST-RECEPTIONIST" not in response.text
        assert "DEMO-0001" not in response.text


def test_cross_facility_denial_is_visible_only_to_patient_facility(client):
    """Only the target patient's facility may list a denied cross-facility read."""
    from app.auth.security import create_access_token

    attempt = client.get(
        "/api/v1/patients/DEMO-0003/workspace",
        headers={
            "Authorization": f"Bearer {create_access_token('TEST-CLINICIAN')}"
        },
    )
    assert attempt.status_code == 404, attempt.text
    assert "clinical_notes" not in attempt.text

    params = {
        "action": "read",
        "resource_type": "patients",
        "resource_id": "DEMO-0003",
    }

    actor_facility = client.get("/api/v1/audit-events", params=params)
    assert actor_facility.status_code == 200, actor_facility.text
    assert actor_facility.json() == []

    target_facility = client.get(
        "/api/v1/audit-events",
        params=params,
        headers={
            "Authorization": (
                f"Bearer {create_access_token('TEST-OTHER-FACILITY-ADMIN')}"
            )
        },
    )
    assert target_facility.status_code == 200, target_facility.text

    events = target_facility.json()
    assert len(events) == 1, events
    assert events[0]["actor_id"] == "TEST-CLINICIAN"
    assert events[0]["resource_id"] == "DEMO-0003"
    assert events[0]["action"] == "read"
    assert events[0]["outcome"] == "denied"
    assert "clinical_notes" not in target_facility.text
