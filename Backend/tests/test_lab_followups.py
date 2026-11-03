"""Tests for synthetic laboratory reports and follow-up task workflows."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def create_encounter(client: TestClient, patient_id: str = "DEMO-0001") -> dict:
    response = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": patient_id,
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Demo Clinician",
            "encounter_type": "consultation",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def report_payload(patient_id: str = "DEMO-0001", encounter_id: str | None = None) -> dict:
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "source_system": "DEMO-LIS",
        "issued_at": "2026-10-28T09:00:00Z",
        "observations": [
            {
                "test_code": "HB",
                "test_name": "Haemoglobin",
                "value_numeric": 12.4,
                "unit": "g/dL",
                "reference_range": "Source-supplied range",
            },
            {
                "test_code": "COMMENT",
                "test_name": "Laboratory comment",
                "value_text": "Synthetic comment only",
            },
        ],
    }


def create_report(client: TestClient, patient_id: str = "DEMO-0001", encounter_id: str | None = None) -> dict:
    response = client.post("/api/v1/lab-results", json=report_payload(patient_id, encounter_id))
    assert response.status_code == 201, response.text
    return response.json()


def set_report_status(client: TestClient, report_id: str, new_status: str):
    return client.patch(f"/api/v1/lab-results/{report_id}/status", json={"status": new_status})


def report_through_review(client: TestClient, report_id: str) -> None:
    for state in ("validated", "awaiting_review", "reviewed"):
        response = set_report_status(client, report_id, state)
        assert response.status_code == 200, response.text


def create_followup(client: TestClient, **overrides) -> dict:
    payload = {
        "patient_id": "DEMO-0001",
        "description": "Synthetic follow-up task for testing",
    }
    payload.update(overrides)
    response = client.post("/api/v1/follow-ups", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# Laboratory report creation and retrieval

def test_create_lab_report_returns_observations(client: TestClient) -> None:
    encounter = create_encounter(client)
    response = client.post(
        "/api/v1/lab-results", json=report_payload(encounter_id=encounter["encounter_id"])
    )
    assert response.status_code == 201
    result = response.json()
    assert result["patient_id"] == "DEMO-0001"
    assert result["encounter_id"] == encounter["encounter_id"]
    assert result["status"] == "received"
    assert len(result["observations"]) == 2
    haemoglobin = next(item for item in result["observations"] if item["test_code"] == "HB")
    assert haemoglobin["value_numeric"] == 12.4


def test_list_lab_reports_and_filter_by_patient_and_status(client: TestClient) -> None:
    first = create_report(client)
    second = create_report(client, patient_id="DEMO-0002")
    response = client.get("/api/v1/lab-results", params={"patient_id": "DEMO-0001", "status": "received"})
    assert response.status_code == 200
    assert [item["report_id"] for item in response.json()] == [first["report_id"]]
    assert second["report_id"] not in [item["report_id"] for item in response.json()]


def test_get_missing_lab_report_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/lab-results/not-a-report")
    assert response.status_code == 404


def test_create_lab_report_for_missing_patient_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/lab-results", json=report_payload("DEMO-9999"))
    assert response.status_code == 404


def test_lab_report_rejects_encounter_for_different_patient(client: TestClient) -> None:
    encounter = create_encounter(client, "DEMO-0002")
    response = client.post(
        "/api/v1/lab-results", json=report_payload("DEMO-0001", encounter["encounter_id"])
    )
    assert response.status_code == 409


def test_lab_report_requires_at_least_one_observation(client: TestClient) -> None:
    payload = report_payload()
    payload["observations"] = []
    response = client.post("/api/v1/lab-results", json=payload)
    assert response.status_code == 422


def test_observation_requires_one_result_value(client: TestClient) -> None:
    payload = report_payload()
    payload["observations"][0].pop("value_numeric")
    payload["observations"][0].pop("unit")
    payload["observations"][0].pop("reference_range")
    response = client.post("/api/v1/lab-results", json=payload)
    assert response.status_code == 422


def test_observation_rejects_both_numeric_and_text_values(client: TestClient) -> None:
    payload = report_payload()
    payload["observations"][0]["value_text"] = "Conflicting representation"
    response = client.post("/api/v1/lab-results", json=payload)
    assert response.status_code == 422


def test_lab_report_rejects_invalid_status_filter(client: TestClient) -> None:
    response = client.get("/api/v1/lab-results", params={"status": "urgent"})
    assert response.status_code == 422


# Laboratory report lifecycle and task linkage

def test_lab_report_valid_status_transitions(client: TestClient) -> None:
    report = create_report(client)
    for state in ("validated", "awaiting_review", "reviewed", "closed"):
        response = set_report_status(client, report["report_id"], state)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == state


def test_lab_report_cannot_skip_validation_and_review(client: TestClient) -> None:
    report = create_report(client)
    response = set_report_status(client, report["report_id"], "reviewed")
    assert response.status_code == 409
    fetched = client.get(f"/api/v1/lab-results/{report['report_id']}")
    assert fetched.json()["status"] == "received"


def test_lab_report_requires_active_task_before_follow_up_required(client: TestClient) -> None:
    report = create_report(client)
    report_through_review(client, report["report_id"])
    response = set_report_status(client, report["report_id"], "follow_up_required")
    assert response.status_code == 409


def test_report_cannot_close_while_linked_followup_is_open(client: TestClient) -> None:
    report = create_report(client)
    report_through_review(client, report["report_id"])
    task = create_followup(client, report_id=report["report_id"])
    response = set_report_status(client, report["report_id"], "follow_up_required")
    assert response.status_code == 200
    response = set_report_status(client, report["report_id"], "closed")
    assert response.status_code == 409
    assert task["status"] == "open"


def test_report_cannot_close_directly_while_linked_followup_is_open(client: TestClient) -> None:
    report = create_report(client)
    report_through_review(client, report["report_id"])
    create_followup(client, report_id=report["report_id"])
    response = set_report_status(client, report["report_id"], "closed")
    assert response.status_code == 409
    assert client.get(f"/api/v1/lab-results/{report['report_id']}").json()["status"] == "reviewed"


def test_report_can_close_after_linked_followup_is_completed(client: TestClient) -> None:
    report = create_report(client)
    report_through_review(client, report["report_id"])
    task = create_followup(client, report_id=report["report_id"])
    assert set_report_status(client, report["report_id"], "follow_up_required").status_code == 200
    started = client.patch(
        f"/api/v1/follow-ups/{task['task_id']}", json={"status": "in_progress"}
    )
    assert started.status_code == 200, started.text
    completed = client.patch(
        f"/api/v1/follow-ups/{task['task_id']}",
        json={"status": "completed", "outcome": "Synthetic outcome recorded"},
    )
    assert completed.status_code == 200, completed.text
    closed = set_report_status(client, report["report_id"], "closed")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_closed_lab_report_cannot_reopen(client: TestClient) -> None:
    report = create_report(client)
    report_through_review(client, report["report_id"])
    assert set_report_status(client, report["report_id"], "closed").status_code == 200
    response = set_report_status(client, report["report_id"], "reviewed")
    assert response.status_code == 409


# Follow-up task creation and linkage

def test_create_unassigned_followup_starts_open(client: TestClient) -> None:
    task = create_followup(client)
    assert task["status"] == "open"
    assert task["assigned_to"] is None
    assert task["closed_at"] is None


def test_create_assigned_followup_starts_assigned(client: TestClient) -> None:
    task = create_followup(client, assigned_to="Demo Nurse")
    assert task["status"] == "assigned"
    assert task["assigned_to"] == "Demo Nurse"


def test_create_followup_rejects_missing_patient(client: TestClient) -> None:
    response = client.post(
        "/api/v1/follow-ups",
        json={"patient_id": "DEMO-9999", "description": "Synthetic task"},
    )
    assert response.status_code == 404


def test_create_followup_rejects_encounter_for_other_patient(client: TestClient) -> None:
    encounter = create_encounter(client, "DEMO-0002")
    response = client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": "DEMO-0001",
            "encounter_id": encounter["encounter_id"],
            "description": "Synthetic task",
        },
    )
    assert response.status_code == 409


def test_lab_followup_requires_report_to_be_reviewed(client: TestClient) -> None:
    report = create_report(client)
    response = client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": "DEMO-0001",
            "report_id": report["report_id"],
            "description": "Synthetic follow-up before review",
        },
    )
    assert response.status_code == 409


def test_list_followups_supports_filters_and_overdue_filter(client: TestClient) -> None:
    due_past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    overdue_task = create_followup(client, due_at=due_past, assigned_to="Demo Nurse")
    create_followup(client, description="Future synthetic task", assigned_to="Demo Nurse")

    response = client.get("/api/v1/follow-ups", params={"assigned_to": "Demo Nurse", "overdue": "true"})
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()] == [overdue_task["task_id"]]


def test_get_missing_followup_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/follow-ups/no-such-task")
    assert response.status_code == 404


def test_task_assignment_updates_open_to_assigned(client: TestClient) -> None:
    task = create_followup(client)
    response = client.patch(
        f"/api/v1/follow-ups/{task['task_id']}", json={"assigned_to": "Demo Nurse"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "assigned"
    assert response.json()["assigned_to"] == "Demo Nurse"


def test_task_cannot_be_completed_without_outcome(client: TestClient) -> None:
    task = create_followup(client, assigned_to="Demo Nurse")
    client.patch(f"/api/v1/follow-ups/{task['task_id']}", json={"status": "in_progress"})
    response = client.patch(f"/api/v1/follow-ups/{task['task_id']}", json={"status": "completed"})
    assert response.status_code == 422
    assert client.get(f"/api/v1/follow-ups/{task['task_id']}").json()["status"] == "in_progress"


def test_task_can_complete_with_outcome_and_sets_closed_time(client: TestClient) -> None:
    task = create_followup(client, assigned_to="Demo Nurse")
    response = client.patch(
        f"/api/v1/follow-ups/{task['task_id']}",
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    response = client.patch(
        f"/api/v1/follow-ups/{task['task_id']}",
        json={"status": "completed", "outcome": "Synthetic outcome recorded"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["closed_at"] is not None


def test_task_rejects_invalid_status_transition(client: TestClient) -> None:
    task = create_followup(client)
    response = client.patch(f"/api/v1/follow-ups/{task['task_id']}", json={"status": "completed"})
    assert response.status_code == 409


def test_completed_task_is_terminal(client: TestClient) -> None:
    task = create_followup(client, assigned_to="Demo Nurse")
    client.patch(
        f"/api/v1/follow-ups/{task['task_id']}",
        json={"status": "in_progress"},
    )
    client.patch(
        f"/api/v1/follow-ups/{task['task_id']}",
        json={"status": "completed", "outcome": "Completed synthetically"},
    )
    response = client.patch(f"/api/v1/follow-ups/{task['task_id']}", json={"outcome": "Changed"})
    assert response.status_code == 409


def test_empty_followup_update_is_rejected(client: TestClient) -> None:
    task = create_followup(client)
    response = client.patch(f"/api/v1/follow-ups/{task['task_id']}", json={})
    assert response.status_code == 422
