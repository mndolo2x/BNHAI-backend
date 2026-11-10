
import pytest

from app.auth.security import create_access_token


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/patient-links",
            {
                "user_id": "TEST-PORTAL-PATIENT",
                "patient_id": "DEMO-0001",
            },
        ),
        (
            "/api/v1/patient-links/TEST-LINK/verify-identity",
            {
                "verification_method": "in_person_document_check",
            },
        ),
        (
            "/api/v1/patient-links/TEST-LINK/approve",
            None,
        ),
    ],
)
def test_portal_patient_cannot_use_staff_patient_link_routes(
    client,
    path,
    payload,
):
    headers = {
        "Authorization": (
            f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
        )
    }

    response = client.post(
        path,
        json=payload,
        headers=headers,
    )

    assert response.status_code == 403, (
        response.status_code,
        response.text,
    )



def test_receptionist_can_enroll_and_verify_but_cannot_approve(client):
    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }

    # 1. Receptionist creates a pending enrollment.
    enrollment = client.post(
        "/api/v1/patient-links",
        json={
            "user_id": "TEST-PORTAL-PATIENT",
            "patient_id": "DEMO-0001",
        },
        headers=receptionist_headers,
    )

    assert enrollment.status_code == 201, enrollment.text

    link = enrollment.json()

    assert link["created_by"] == "TEST-RECEPTIONIST"
    assert link["verification_status"] == "pending"

    link_id = link["link_id"]

    # 2. Receptionist records an identity check.
    identity_check = client.post(
        f"/api/v1/patient-links/{link_id}/verify-identity",
        json={
            "verification_method": "in_person_document_check"
        },
        headers=receptionist_headers,
    )

    assert identity_check.status_code == 201, identity_check.text
    assert identity_check.json()["verified_by"] == "TEST-RECEPTIONIST"

    # 3. Receptionist attempts approval.
    approval = client.post(
        f"/api/v1/patient-links/{link_id}/approve",
        headers=receptionist_headers,
    )

    assert approval.status_code == 403, approval.text

    # 4. Patient still cannot access the portal.
    portal_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
    }

    profile = client.get(
        "/api/v1/portal/me",
        headers=portal_headers,
    )

    assert profile.status_code == 403, profile.text




def test_end_to_end_patient_link_approval_unlocks_portal(client):
    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    administrator_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-FACILITY-ADMIN')}"
    }
    patient_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
    }

    # 1. Receptionist initiates patient enrollment.
    enrollment = client.post(
        "/api/v1/patient-links",
        json={
            "user_id": "TEST-PORTAL-PATIENT",
            "patient_id": "DEMO-0001",
        },
        headers=receptionist_headers,
    )

    assert enrollment.status_code == 201, enrollment.text

    link = enrollment.json()
    assert link["verification_status"] == "pending"
    assert link["created_by"] == "TEST-RECEPTIONIST"

    link_id = link["link_id"]

    # 2. Receptionist records identity verification.
    identity = client.post(
        f"/api/v1/patient-links/{link_id}/verify-identity",
        json={
            "verification_method": "in_person_document_check"
        },
        headers=receptionist_headers,
    )

    assert identity.status_code == 201, identity.text
    assert identity.json()["link_id"] == link_id

    # Patient must not have access before approval.
    before_approval = client.get(
        "/api/v1/portal/me",
        headers=patient_headers,
    )

    assert before_approval.status_code == 403, before_approval.text

    # 3. Separate facility administrator approves enrollment.
    approval = client.post(
        f"/api/v1/patient-links/{link_id}/approve",
        headers=administrator_headers,
    )

    assert approval.status_code == 200, approval.text

    approved = approval.json()
    assert approved["verification_status"] == "verified"
    assert approved["verified_by"] == "TEST-FACILITY-ADMIN"
    assert approved["verified_at"] is not None

    # 4. Patient can now access their verified portal profile.
    after_approval = client.get(
        "/api/v1/portal/me",
        headers=patient_headers,
    )

    assert after_approval.status_code == 200, after_approval.text

    profile = after_approval.json()
    assert profile["user_id"] == "TEST-PORTAL-PATIENT"
    assert "DEMO-0001" in profile["patient_ids"]




def test_other_facility_admin_cannot_approve_via_api(client):
    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    other_admin_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-OTHER-FACILITY-ADMIN')}"
    }
    patient_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
    }

    # Receptionist creates an enrollment.
    enrollment = client.post(
        "/api/v1/patient-links",
        json={
            "user_id": "TEST-PORTAL-PATIENT",
            "patient_id": "DEMO-0001",
        },
        headers=receptionist_headers,
    )
    assert enrollment.status_code == 201, enrollment.text
    link_id = enrollment.json()["link_id"]

    # Receptionist records the identity check.
    verification = client.post(
        f"/api/v1/patient-links/{link_id}/verify-identity",
        json={"verification_method": "in_person_document_check"},
        headers=receptionist_headers,
    )
    assert verification.status_code == 201, verification.text

    # Administrator from another facility attempts approval.
    denied = client.post(
        f"/api/v1/patient-links/{link_id}/approve",
        headers=other_admin_headers,
    )
    assert denied.status_code == 404, denied.text

    # Patient must still be denied portal access.
    profile = client.get(
        "/api/v1/portal/me",
        headers=patient_headers,
    )
    assert profile.status_code == 403, profile.text





def test_facility_admin_cannot_approve_own_enrollment_via_api(client):
    admin_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-FACILITY-ADMIN')}"
    }
    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    patient_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
    }

    # Administrator initiates the enrollment.
    enrollment = client.post(
        "/api/v1/patient-links",
        json={
            "user_id": "TEST-PORTAL-PATIENT",
            "patient_id": "DEMO-0001",
        },
        headers=admin_headers,
    )

    assert enrollment.status_code == 201, enrollment.text
    link_id = enrollment.json()["link_id"]
    assert enrollment.json()["created_by"] == "TEST-FACILITY-ADMIN"

    # A different staff member performs the identity check.
    check = client.post(
        f"/api/v1/patient-links/{link_id}/verify-identity",
        json={"verification_method": "in_person_document_check"},
        headers=receptionist_headers,
    )

    assert check.status_code == 201, check.text

    # The administrator attempts to approve their own enrollment.
    denied = client.post(
        f"/api/v1/patient-links/{link_id}/approve",
        headers=admin_headers,
    )

    assert denied.status_code == 403, denied.text

    # The patient must still be denied portal access.
    profile = client.get(
        "/api/v1/portal/me",
        headers=patient_headers,
    )

    assert profile.status_code == 403, profile.text




def test_identity_verifier_cannot_approve_own_check_via_api(client):
    receptionist_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"
    }
    admin_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-FACILITY-ADMIN')}"
    }
    patient_headers = {
        "Authorization": f"Bearer {create_access_token('TEST-PORTAL-PATIENT')}"
    }

    # Receptionist initiates the enrollment.
    enrollment = client.post(
        "/api/v1/patient-links",
        json={
            "user_id": "TEST-PORTAL-PATIENT",
            "patient_id": "DEMO-0001",
        },
        headers=receptionist_headers,
    )
    assert enrollment.status_code == 201, enrollment.text
    link_id = enrollment.json()["link_id"]

    # Administrator performs the identity check.
    check = client.post(
        f"/api/v1/patient-links/{link_id}/verify-identity",
        json={"verification_method": "in_person_document_check"},
        headers=admin_headers,
    )
    assert check.status_code == 201, check.text
    assert check.json()["verified_by"] == "TEST-FACILITY-ADMIN"

    # The same administrator attempts approval.
    denied = client.post(
        f"/api/v1/patient-links/{link_id}/approve",
        headers=admin_headers,
    )
    assert denied.status_code == 403, denied.text

    # Patient access must remain blocked.
    profile = client.get(
        "/api/v1/portal/me",
        headers=patient_headers,
    )
    assert profile.status_code == 403, profile.text
