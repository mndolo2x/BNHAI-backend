"""Tests for secure PDF invoice capture and claim batch preparation."""
from io import BytesIO
from uuid import uuid4

from reportlab.pdfgen import canvas

from app.auth.security import create_access_token


def auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def make_invoice_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in text.splitlines():
        pdf.drawString(40, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


INVOICE_TEXT = """Invoice Number: INV-TEST-001
Member Surname and Initials: SMITH J
Patient First Name: JANE
Benefit Option: Standard
Membership Number: 123456789
Practice Code: 9914999
Practice Name: Example Medical Practice
Provider Name: Dr A Example
Date of Service: 29/10/2026
Nature of Service: General consultation
ICD-10: I10
Tariff Code: 0019
Quantity: 1
Amount: P450.00"""


def upload_pdf(client, content: bytes, *, name="invoice.pdf", facility="DEMO-FACILITY-001", user="TEST-RECEPTIONIST"):
    return client.post(
        "/api/v1/claims/documents",
        data={"facility_id": facility},
        files=[("files", (name, content, "application/pdf"))],
        headers=auth(user),
    )


def test_receptionist_can_upload_and_extract_text_pdf(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMS_STORAGE_DIR", str(tmp_path / "claim-files"))
    response = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received_count"] == 1
    assert body["rejected"] == []
    document = body["uploaded"][0]
    assert document["extraction_status"] == "extracted"
    assert document["claim_status"] == "needs_review"
    assert document["extracted_fields"]["membership_number"] == "123456789"
    assert document["extracted_fields"]["patient_first_name"] == "JANE"
    assert document["extracted_fields"]["tariff_code"] == "0019"
    assert document["extracted_fields"]["amount"] == 450.0
    assert "member_signature_confirmed" in document["validation"]["warnings"][0] or any(
        "signature" in warning.lower() for warning in document["validation"]["warnings"]
    )
    stored_files = list((tmp_path / "claim-files").rglob("*.pdf"))
    assert len(stored_files) == 1


def test_bulk_upload_accepts_multiple_and_rejects_non_pdf(client):
    first = make_invoice_pdf(INVOICE_TEXT)
    second = make_invoice_pdf(INVOICE_TEXT.replace("INV-TEST-001", "INV-TEST-002").replace("P450.00", "P300.00"))
    response = client.post(
        "/api/v1/claims/documents",
        data={"facility_id": "DEMO-FACILITY-001"},
        files=[
            ("files", ("one.pdf", first, "application/pdf")),
            ("files", ("two.pdf", second, "application/pdf")),
            ("files", ("notes.txt", b"not a pdf", "text/plain")),
        ],
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received_count"] == 3
    assert len(body["uploaded"]) == 2
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["filename"] == "notes.txt"


def test_scanned_pdf_is_stored_and_flagged_for_ocr(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMS_STORAGE_DIR", str(tmp_path / "claim-files"))
    scanned = make_invoice_pdf("")
    response = upload_pdf(client, scanned)
    assert response.status_code == 201
    document = response.json()["uploaded"][0]
    assert document["extraction_status"] == "needs_ocr"
    assert document["claim_status"] == "needs_review"
    assert any("OCR" in item for item in document["validation"]["warnings"])


def test_exact_duplicate_pdf_is_flagged_instead_of_saved_again(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMS_STORAGE_DIR", str(tmp_path / "claim-files"))
    content = make_invoice_pdf(INVOICE_TEXT)
    first = upload_pdf(client, content).json()["uploaded"][0]
    second = upload_pdf(client, content).json()["uploaded"][0]
    assert second["claim_status"] == "duplicate"
    assert second["extraction_status"] == "duplicate"
    assert second["duplicate_of"] == first["claim_document_id"]
    assert second["validation"]["can_approve"] is False


def test_upload_rejects_invalid_pdf_content(client):
    response = upload_pdf(client, b"not really a PDF")
    assert response.status_code == 201
    assert response.json()["uploaded"] == []
    assert response.json()["rejected"][0]["error"] == "The uploaded file is not a valid PDF document."


def test_upload_requires_claim_permission_and_facility_assignment(client):
    denied_role = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT), user="TEST-LAB-WORKER")
    assert denied_role.status_code == 403
    outside_facility = upload_pdf(
        client, make_invoice_pdf(INVOICE_TEXT), facility="DEMO-FACILITY-002", user="TEST-RECEPTIONIST"
    )
    assert outside_facility.status_code == 403


def test_receptionist_can_review_corrected_fields_but_only_clinician_or_admin_approves(client):
    uploaded = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT)).json()["uploaded"][0]
    document_id = uploaded["claim_document_id"]
    corrected = client.patch(
        f"/api/v1/claims/documents/{document_id}",
        json={"fields": {"member_signature_confirmed": True}},
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["claim_status"] == "ready_for_approval"

    forbidden = client.post(
        f"/api/v1/claims/documents/{document_id}/approve",
        json={"member_signature_confirmed": True},
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert forbidden.status_code == 403

    approved = client.post(
        f"/api/v1/claims/documents/{document_id}/approve",
        json={"member_signature_confirmed": True, "provider_signature_confirmed": True},
        headers=auth("TEST-CLINICIAN"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["claim_status"] == "approved"
    assert approved.json()["validation"]["can_approve"] is True


def test_document_cannot_be_approved_until_missing_fields_are_corrected(client):
    pdf = make_invoice_pdf(INVOICE_TEXT.replace("Membership Number: 123456789\n", ""))
    uploaded = upload_pdf(client, pdf).json()["uploaded"][0]
    document_id = uploaded["claim_document_id"]
    response = client.post(
        f"/api/v1/claims/documents/{document_id}/approve",
        json={"member_signature_confirmed": True},
        headers=auth("TEST-CLINICIAN"),
    )
    assert response.status_code == 409
    assert "membership_number" in response.json()["detail"]["validation"]["missing_fields"]


def test_document_list_and_download_are_facility_scoped(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMS_STORAGE_DIR", str(tmp_path / "claim-files"))
    uploaded = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT)).json()["uploaded"][0]
    doc_id = uploaded["claim_document_id"]
    listed = client.get("/api/v1/claims/documents", headers=auth("TEST-RECEPTIONIST"))
    assert listed.status_code == 200
    assert doc_id in {item["claim_document_id"] for item in listed.json()}
    downloaded = client.get(f"/api/v1/claims/documents/{doc_id}/file", headers=auth("TEST-RECEPTIONIST"))
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF-")
    cross_facility = client.get(
        "/api/v1/claims/documents?facility_id=DEMO-FACILITY-002", headers=auth("TEST-RECEPTIONIST")
    )
    assert cross_facility.status_code == 404


def test_approved_documents_can_be_batched_exported_and_recorded_externally(client):
    uploaded_a = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT)).json()["uploaded"][0]
    uploaded_b = upload_pdf(
        client,
        make_invoice_pdf(INVOICE_TEXT.replace("INV-TEST-001", "INV-TEST-002").replace("P450.00", "P300.00")),
    ).json()["uploaded"][0]

    for item in (uploaded_a, uploaded_b):
        document_id = item["claim_document_id"]
        corrected = client.patch(
            f"/api/v1/claims/documents/{document_id}",
            json={"fields": {"member_signature_confirmed": True}},
            headers=auth("TEST-RECEPTIONIST"),
        )
        assert corrected.status_code == 200
        approved = client.post(
            f"/api/v1/claims/documents/{document_id}/approve",
            json={"member_signature_confirmed": True},
            headers=auth("TEST-FACILITY-ADMIN"),
        )
        assert approved.status_code == 200

    batch_response = client.post(
        "/api/v1/claims/batches",
        json={
            "facility_id": "DEMO-FACILITY-001",
            "claim_document_ids": [uploaded_a["claim_document_id"], uploaded_b["claim_document_id"]],
        },
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()
    assert batch["document_count"] == 2
    assert batch["total_amount"] == 750.0
    assert batch["status"] == "prepared"

    export = client.post(
        f"/api/v1/claims/batches/{batch['batch_id']}/export-review-csv",
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert export.status_code == 200
    assert export.headers["x-bnhai-export-warning"].startswith("INTERNAL REVIEW EXPORT ONLY")
    assert "NOT A BPOMAS" in export.headers["x-bnhai-export-warning"]
    assert b"INV-TEST-001" in export.content
    assert "INTERNAL_REVIEW_ONLY" in export.headers["content-disposition"]

    submitted = client.post(
        f"/api/v1/claims/batches/{batch['batch_id']}/record-external-submission",
        json={
            "external_submission_reference": "EMAIL-TEST-0001",
            "external_submission_channel": "email",
            "acknowledgement_notes": "Recorded as submitted outside BNHAI for test purposes.",
        },
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted_externally"

    acknowledged = client.post(
        f"/api/v1/claims/batches/{batch['batch_id']}/record-acknowledgement",
        json={"outcome": "accepted", "notes": "Synthetic acceptance acknowledgement for test only."},
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "acknowledged"

    detail = client.get(f"/api/v1/claims/batches/{batch['batch_id']}", headers=auth("TEST-AUDITOR"))
    assert detail.status_code == 200
    assert detail.json()["external_submission_reference"] == "EMAIL-TEST-0001"
    assert detail.json()["acknowledgement_notes"] == "Synthetic acceptance acknowledgement for test only."


def test_batch_cannot_include_unapproved_or_cross_facility_document(client):
    upload = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT)).json()["uploaded"][0]
    response = client.post(
        "/api/v1/claims/batches",
        json={"facility_id": "DEMO-FACILITY-001", "claim_document_ids": [upload["claim_document_id"]]},
        headers=auth("TEST-FACILITY-ADMIN"),
    )
    assert response.status_code == 409


def test_batch_create_is_restricted_to_facility_admin(client):
    response = client.post(
        "/api/v1/claims/batches",
        json={"facility_id": "DEMO-FACILITY-001", "claim_document_ids": [str(uuid4())]},
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert response.status_code == 403


def test_claim_document_update_rejects_unknown_fields(client):
    uploaded = upload_pdf(client, make_invoice_pdf(INVOICE_TEXT)).json()["uploaded"][0]
    response = client.patch(
        f"/api/v1/claims/documents/{uploaded['claim_document_id']}",
        json={"fields": {"invented_bpomas_flag": True}},
        headers=auth("TEST-RECEPTIONIST"),
    )
    assert response.status_code == 422


def test_business_key_duplicate_is_detected_when_pdf_file_hash_differs(client):
    original = make_invoice_pdf(INVOICE_TEXT)
    uploaded = upload_pdf(client, original).json()["uploaded"][0]
    # Change non-claim text so that the PDF bytes differ, while invoice identity fields remain identical.
    resaved = make_invoice_pdf("COPY FOR RECORDS\n" + INVOICE_TEXT)
    assert resaved != original
    duplicate = upload_pdf(client, resaved).json()["uploaded"][0]
    assert duplicate["claim_status"] == "needs_review"
    assert duplicate["duplicate_of"] == uploaded["claim_document_id"]
    assert any("Possible duplicate" in item for item in duplicate["validation"]["warnings"])
