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
