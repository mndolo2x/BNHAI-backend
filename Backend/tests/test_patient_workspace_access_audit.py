"""Security regression for auditing sensitive patient-workspace reads."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import create_access_token
from app.db.models import AuditEventRecord
from app.db.session import get_db


def test_successful_patient_workspace_read_is_audited(client: TestClient) -> None:
    """A clinician opening a workspace must leave a metadata-only audit event."""
    patient_id = "DEMO-0001"
    user_id = "TEST-CLINICIAN"
    token = create_access_token(user_id)

    response = client.get(
        f"/api/v1/patients/{patient_id}/workspace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text

    session_generator = client.app.dependency_overrides[get_db]()
    db = next(session_generator)
    try:
        events = db.scalars(
            select(AuditEventRecord).where(
                AuditEventRecord.actor_id == user_id,
                AuditEventRecord.action == "read",
                AuditEventRecord.resource_type == "patients",
                AuditEventRecord.resource_id == patient_id,
                AuditEventRecord.outcome == "success",
            )
        ).all()

        assert len(events) == 1, (
            f"Expected one successful workspace-read audit event, got {len(events)}"
        )
        assert events[0].actor_source == "authenticated-user"
    finally:
        session_generator.close()


def test_workspace_read_fails_closed_when_audit_storage_fails(
    client: TestClient, monkeypatch
) -> None:
    """A failed audit write must not return patient information."""
    from sqlalchemy.exc import OperationalError
    from app.api.v1 import patient_workspace as workspace_module

    original_session_class = workspace_module.Session

    class UnavailableAuditSession(original_session_class):
        def commit(self) -> None:
            raise OperationalError(
                "simulated audit insert",
                {},
                RuntimeError("simulated audit storage failure"),
            )

    monkeypatch.setattr(
        workspace_module,
        "Session",
        UnavailableAuditSession,
    )

    token = create_access_token("TEST-CLINICIAN")

    with TestClient(
        client.app,
        raise_server_exceptions=False,
    ) as probe:
        response = probe.get(
            "/api/v1/patients/DEMO-0001/workspace",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503, response.status_code
    assert "DEMO-0001" not in response.text
    assert "clinical_notes" not in response.text


def test_cross_facility_and_unknown_workspace_denials_are_audited(client: TestClient) -> None:
    """Both kinds of 404 denial should produce metadata-only audit records."""
    actor_id = "TEST-PLATFORM-ADMIN"
    patient_ids = ("DEMO-0003", "DEMO-NOT-FOUND")
    headers = {"Authorization": f"Bearer {create_access_token(actor_id)}"}

    for patient_id in patient_ids:
        response = client.get(
            f"/api/v1/patients/{patient_id}/workspace",
            headers=headers,
        )
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "Patient not found"}

    generator = client.app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        for patient_id in patient_ids:
            events = db.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.actor_id == actor_id,
                    AuditEventRecord.actor_source == "authenticated-user",
                    AuditEventRecord.action == "read",
                    AuditEventRecord.resource_type == "patients",
                    AuditEventRecord.resource_id == patient_id,
                    AuditEventRecord.outcome == "denied",
                )
            ).all()

            assert len(events) == 1, (
                f"Expected one denied-read audit event for {patient_id}, "
                f"got {len(events)}"
            )
            assert events[0].occurred_at is not None
    finally:
        generator.close()
