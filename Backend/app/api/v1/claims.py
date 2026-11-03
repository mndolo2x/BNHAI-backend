"""Invoice capture and claim-batch preparation APIs.

This module prepares claim data for staff review. It does NOT submit claims to
BPOMAS or generate a BPOMAS-certified XML/MIP/CSV interchange file.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids, require_assigned_facility
from app.db.models import ClaimBatchRecord, ClaimDocumentRecord, FacilityRecord
from app.db.session import get_db
from app.models.claims import (
    ClaimApprovalRequest,
    ClaimBatchAcknowledgement,
    ClaimBatchCreate,
    ClaimBatchExternalSubmission,
    ClaimBatchRead,
    ClaimDocumentRead,
    ClaimDocumentUpdate,
    ClaimExtractedFields,
    ClaimUploadFailure,
    ClaimUploadResult,
    ClaimValidation,
)
from app.services.claim_extraction import (
    MAX_PDF_BYTES,
    extract_claim_fields,
    extract_pdf_text,
    validate_claim_fields,
)
from app.services.notifications import notify_facility_roles

router = APIRouter(prefix="/claims", tags=["BPOMAS Claims Capture"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

CLAIM_READ_ROLES = {"receptionist", "clinician", "nurse", "facility_admin", "auditor", "platform_admin"}
CLAIM_UPLOAD_ROLES = {"receptionist", "facility_admin", "platform_admin"}
CLAIM_REVIEW_ROLES = {"clinician", "facility_admin", "platform_admin"}
CLAIM_BATCH_ROLES = {"facility_admin", "platform_admin"}
MAX_UPLOAD_COUNT = 100
MAX_BULK_BYTES = 100 * 1024 * 1024


def _storage_root() -> Path:
    configured = os.getenv("CLAIMS_STORAGE_DIR", "./data/claims")
    root = Path(configured).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "invoice.pdf").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:255]
    return name or "invoice.pdf"


def _document_path(storage_key: str) -> Path:
    root = _storage_root()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=500, detail="Stored document path is invalid.")
    return target


def _serialize_document(document: ClaimDocumentRecord) -> ClaimDocumentRead:
    extracted = json.loads(document.extracted_fields_json or "{}")
    validation = json.loads(document.validation_json or "{}")
    return ClaimDocumentRead(
        claim_document_id=document.claim_document_id,
        facility_id=document.facility_id,
        original_filename=document.original_filename,
        sha256=document.sha256,
        file_size_bytes=document.file_size_bytes,
        page_count=document.page_count,
        extraction_status=document.extraction_status,
        claim_status=document.claim_status,
        extracted_fields=ClaimExtractedFields.model_validate(extracted),
        validation=ClaimValidation.model_validate(validation),
        batch_id=document.batch_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        duplicate_of=validation.get("duplicate_of") or validation.get("possible_duplicate_of"),
    )


def _serialize_batch(batch: ClaimBatchRecord) -> ClaimBatchRead:
    return ClaimBatchRead.model_validate(batch, from_attributes=True)


def _require_facility_role(user: AuthenticatedUser, facility_id: str, roles: set[str]) -> None:
    require_assigned_facility(user, facility_id, roles)


def _get_document(document_id: str, db: Session, user: AuthenticatedUser, roles: set[str]) -> ClaimDocumentRecord:
    document = db.get(ClaimDocumentRecord, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Claim document not found.")
    _require_facility_role(user, document.facility_id, roles)
    return document


def _get_batch(batch_id: str, db: Session, user: AuthenticatedUser, roles: set[str]) -> ClaimBatchRecord:
    batch = db.get(ClaimBatchRecord, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Claim batch not found.")
    _require_facility_role(user, batch.facility_id, roles)
    return batch


def _write_pdf(storage_key: str, content: bytes) -> None:
    target = _document_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


@router.post(
    "/documents",
    response_model=ClaimUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or many invoice PDFs for extraction",
    description=(
        "Accepts one invoice or a bulk set of invoice PDFs (up to 100 per request). "
        "Text-based PDFs are parsed. Scanned PDFs are stored and marked needs_ocr; this version does not claim to OCR them."
    ),
)
async def upload_claim_documents(
    facility_id: Annotated[str, Form(min_length=2, max_length=80)],
    files: Annotated[list[UploadFile], File(description="One invoice PDF or a bulk set of invoice PDFs")],
    db: DbSession,
    user: CurrentUser,
) -> ClaimUploadResult:
    _require_facility_role(user, facility_id, CLAIM_UPLOAD_ROLES)
    if db.get(FacilityRecord, facility_id) is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    if not files:
        raise HTTPException(status_code=422, detail="Upload at least one PDF invoice.")
    if len(files) > MAX_UPLOAD_COUNT:
        raise HTTPException(status_code=413, detail=f"A bulk upload may contain at most {MAX_UPLOAD_COUNT} files.")

    uploaded: list[ClaimDocumentRead] = []
    rejected: list[ClaimUploadFailure] = []
    total_bytes = 0
    for upload in files:
        filename = _safe_filename(upload.filename)
        if not filename.lower().endswith(".pdf"):
            rejected.append(ClaimUploadFailure(filename=filename, error="Only PDF invoices are accepted."))
            continue
        content = await upload.read(MAX_PDF_BYTES + 1)
        await upload.close()
        if len(content) > MAX_PDF_BYTES:
            rejected.append(ClaimUploadFailure(filename=filename, error="PDF exceeds the 20 MB file limit."))
            continue
        if total_bytes + len(content) > MAX_BULK_BYTES:
            rejected.append(ClaimUploadFailure(filename=filename, error="Bulk upload total exceeds the 100 MB request limit."))
            continue
        total_bytes += len(content)
        try:
            extracted_text, page_count = extract_pdf_text(content)
        except ValueError as exc:
            rejected.append(ClaimUploadFailure(filename=filename, error=str(exc)))
            continue

        digest = hashlib.sha256(content).hexdigest()
        exact_duplicate = db.scalar(
            select(ClaimDocumentRecord).where(
                ClaimDocumentRecord.facility_id == facility_id,
                ClaimDocumentRecord.sha256 == digest,
                ClaimDocumentRecord.claim_status != "duplicate",
            ).limit(1)
        )
        # Business-key matches are only possible duplicates: two legitimate invoices
        # can share a date, patient, tariff and amount. Keep them for human review.
        parsed_for_duplicate = extract_claim_fields(extracted_text) if extracted_text else {}
        possible_duplicate = None
        if exact_duplicate is None and parsed_for_duplicate.get("invoice_number") and parsed_for_duplicate.get("membership_number"):
            possible_duplicate = db.scalar(
                select(ClaimDocumentRecord).where(
                    ClaimDocumentRecord.facility_id == facility_id,
                    ClaimDocumentRecord.invoice_number == parsed_for_duplicate["invoice_number"],
                    ClaimDocumentRecord.membership_number == parsed_for_duplicate["membership_number"],
                    ClaimDocumentRecord.claim_status != "duplicate",
                ).limit(1)
            )
        if exact_duplicate is None and possible_duplicate is None and all(parsed_for_duplicate.get(key) not in (None, "") for key in (
            "membership_number", "service_date", "patient_first_name", "tariff_code", "amount"
        )):
            possible_duplicate = db.scalar(
                select(ClaimDocumentRecord).where(
                    ClaimDocumentRecord.facility_id == facility_id,
                    ClaimDocumentRecord.membership_number == parsed_for_duplicate["membership_number"],
                    ClaimDocumentRecord.service_date == parsed_for_duplicate["service_date"],
                    ClaimDocumentRecord.patient_first_name == parsed_for_duplicate["patient_first_name"],
                    ClaimDocumentRecord.tariff_code == parsed_for_duplicate["tariff_code"],
                    ClaimDocumentRecord.amount == parsed_for_duplicate["amount"],
                    ClaimDocumentRecord.claim_status != "duplicate",
                ).limit(1)
            )
        document_id = str(uuid4())
        if exact_duplicate is not None:
            validation = {
                "errors": ["This exact PDF has already been uploaded to this facility."],
                "warnings": [],
                "missing_fields": [],
                "can_approve": False,
                "validation_scope": "Exact duplicate file detection by SHA-256 checksum.",
                "duplicate_of": exact_duplicate.claim_document_id,
            }
            document = ClaimDocumentRecord(
                claim_document_id=document_id,
                facility_id=facility_id,
                uploaded_by=user.user_id,
                original_filename=filename,
                storage_key=None,
                sha256=digest,
                invoice_number=parsed_for_duplicate.get("invoice_number"),
                membership_number=parsed_for_duplicate.get("membership_number"),
                service_date=parsed_for_duplicate.get("service_date"),
                patient_first_name=parsed_for_duplicate.get("patient_first_name"),
                tariff_code=parsed_for_duplicate.get("tariff_code"),
                amount=parsed_for_duplicate.get("amount"),
                file_size_bytes=len(content),
                page_count=page_count,
                extraction_status="duplicate",
                claim_status="duplicate",
                extracted_fields_json="{}",
                validation_json=json.dumps(validation),
            )
            db.add(document)
            db.flush()
            uploaded.append(_serialize_document(document))
            continue

        fields = extract_claim_fields(extracted_text) if extracted_text else ClaimExtractedFields().model_dump(mode="json")
        validation = validate_claim_fields(fields)
        if possible_duplicate is not None:
            validation["warnings"].append(
                "Possible duplicate: invoice/member details match an existing claim. A human reviewer must compare both documents before approval."
            )
            validation["possible_duplicate_of"] = possible_duplicate.claim_document_id
        if not extracted_text:
            extraction_status = "needs_ocr"
            validation["warnings"].append(
                "No selectable text was found. This appears to be a scanned/image PDF and requires OCR before automated extraction."
            )
        else:
            extraction_status = "extracted"
        claim_status = "ready_for_approval" if validation["can_approve"] else "needs_review"
        storage_key = f"{document_id[:2]}/{document_id}.pdf"
        _write_pdf(storage_key, content)
        document = ClaimDocumentRecord(
            claim_document_id=document_id,
            facility_id=facility_id,
            uploaded_by=user.user_id,
            original_filename=filename,
            storage_key=storage_key,
            sha256=digest,
            invoice_number=fields.get("invoice_number"),
            membership_number=fields.get("membership_number"),
            service_date=fields.get("service_date"),
            patient_first_name=fields.get("patient_first_name"),
            tariff_code=fields.get("tariff_code"),
            amount=fields.get("amount"),
            file_size_bytes=len(content),
            page_count=page_count,
            extraction_status=extraction_status,
            claim_status=claim_status,
            extracted_fields_json=json.dumps(fields),
            validation_json=json.dumps(validation),
        )
        db.add(document)
        db.flush()
        uploaded.append(_serialize_document(document))

    if uploaded:
        notify_facility_roles(
            db,
            facility_id=facility_id,
            roles={"facility_admin"},
            category="administration",
            title="Invoice documents uploaded",
            message=f"{len(uploaded)} invoice document(s) were added to the claims review queue.",
            resource_type="claim_documents",
            resource_id=uploaded[0].claim_document_id if len(uploaded) == 1 else None,
            exclude_user_id=user.user_id,
        )
    db.commit()
    return ClaimUploadResult(uploaded=uploaded, rejected=rejected, received_count=len(files))


@router.get("/documents", response_model=list[ClaimDocumentRead], summary="List claim documents within authorised facilities")
def list_claim_documents(
    db: DbSession,
    user: CurrentUser,
    facility_id: str | None = None,
    claim_status: str | None = None,
    limit: int = 50,
) -> list[ClaimDocumentRead]:
    limit = max(1, min(limit, 200))
    allowed_facilities = assigned_facility_ids(user, CLAIM_READ_ROLES)
    if facility_id:
        if facility_id not in allowed_facilities:
            raise HTTPException(status_code=404, detail="Claim documents not found.")
        allowed_facilities = {facility_id}
    statement = select(ClaimDocumentRecord).where(ClaimDocumentRecord.facility_id.in_(allowed_facilities))
    if claim_status:
        allowed_statuses = {"needs_review", "ready_for_approval", "approved", "batched", "submitted_externally", "duplicate"}
        if claim_status not in allowed_statuses:
            raise HTTPException(status_code=422, detail="Unsupported claim status filter.")
        statement = statement.where(ClaimDocumentRecord.claim_status == claim_status)
    rows = db.scalars(statement.order_by(ClaimDocumentRecord.created_at.desc()).limit(limit)).all()
    return [_serialize_document(item) for item in rows]


@router.get("/documents/{document_id}", response_model=ClaimDocumentRead, summary="Read one claim document and extracted fields")
def get_claim_document(document_id: str, db: DbSession, user: CurrentUser) -> ClaimDocumentRead:
    return _serialize_document(_get_document(document_id, db, user, CLAIM_READ_ROLES))


@router.get("/documents/{document_id}/file", summary="Download the original invoice PDF")
def download_claim_document(document_id: str, db: DbSession, user: CurrentUser) -> FileResponse:
    document = _get_document(document_id, db, user, CLAIM_READ_ROLES)
    if not document.storage_key:
        raise HTTPException(status_code=409, detail="A stored PDF is not available for this duplicate record.")
    path = _document_path(document.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The stored invoice file could not be found.")
    return FileResponse(path, media_type="application/pdf", filename=document.original_filename)


@router.patch("/documents/{document_id}", response_model=ClaimDocumentRead, summary="Correct extracted invoice fields")
def update_claim_document(
    document_id: str,
    payload: ClaimDocumentUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ClaimDocumentRead:
    document = _get_document(document_id, db, user, CLAIM_UPLOAD_ROLES)
    if document.claim_status in {"approved", "batched", "submitted_externally", "duplicate"}:
        raise HTTPException(status_code=409, detail="This claim can no longer be edited in its current status.")
    existing = json.loads(document.extracted_fields_json or "{}")
    try:
        patch_fields = payload.fields.model_dump(exclude_unset=True, mode="json")
        merged = ClaimExtractedFields.model_validate({**existing, **patch_fields}).model_dump(mode="json")
    except Exception as exc:
        raise HTTPException(status_code=422, detail="One or more extracted fields are invalid.") from exc
    validation = validate_claim_fields(merged)
    document.extracted_fields_json = json.dumps(merged)
    document.invoice_number = merged.get("invoice_number")
    document.membership_number = merged.get("membership_number")
    document.service_date = merged.get("service_date")
    document.patient_first_name = merged.get("patient_first_name")
    document.tariff_code = merged.get("tariff_code")
    document.amount = merged.get("amount")
    document.validation_json = json.dumps(validation)
    document.claim_status = "ready_for_approval" if validation["can_approve"] else "needs_review"
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return _serialize_document(document)


@router.post("/documents/{document_id}/approve", response_model=ClaimDocumentRead, summary="Approve invoice data after human verification")
def approve_claim_document(
    document_id: str,
    payload: ClaimApprovalRequest,
    db: DbSession,
    user: CurrentUser,
) -> ClaimDocumentRead:
    document = _get_document(document_id, db, user, CLAIM_REVIEW_ROLES)
    if document.claim_status not in {"needs_review", "ready_for_approval"}:
        raise HTTPException(status_code=409, detail="This claim is not awaiting approval.")
    fields = json.loads(document.extracted_fields_json or "{}")
    fields["member_signature_confirmed"] = payload.member_signature_confirmed
    if payload.provider_signature_confirmed is not None:
        fields["provider_signature_confirmed"] = payload.provider_signature_confirmed
    if payload.referral_document_confirmed is not None:
        fields["referral_document_confirmed"] = payload.referral_document_confirmed
    validation = validate_claim_fields(fields)
    if not validation["can_approve"]:
        raise HTTPException(
            status_code=409,
            detail={"message": "The invoice cannot be approved until required fields are complete and the member acknowledgement is confirmed.", "validation": validation},
        )
    document.extracted_fields_json = json.dumps(fields)
    document.validation_json = json.dumps(validation)
    document.claim_status = "approved"
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return _serialize_document(document)


@router.post("/batches", response_model=ClaimBatchRead, status_code=status.HTTP_201_CREATED, summary="Prepare a batch from approved invoices")
def create_claim_batch(payload: ClaimBatchCreate, db: DbSession, user: CurrentUser) -> ClaimBatchRead:
    _require_facility_role(user, payload.facility_id, CLAIM_BATCH_ROLES)
    if db.get(FacilityRecord, payload.facility_id) is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    docs = db.scalars(
        select(ClaimDocumentRecord).where(ClaimDocumentRecord.claim_document_id.in_(payload.claim_document_ids))
    ).all()
    if len(docs) != len(payload.claim_document_ids):
        raise HTTPException(status_code=404, detail="One or more claim documents were not found.")
    if any(item.facility_id != payload.facility_id for item in docs):
        raise HTTPException(status_code=404, detail="One or more claim documents were not found.")
    if any(item.claim_status != "approved" or item.batch_id is not None for item in docs):
        raise HTTPException(status_code=409, detail="Only approved, unbatched invoices can be included in a batch.")
    total = 0.0
    for item in docs:
        fields = json.loads(item.extracted_fields_json or "{}")
        total += float(fields.get("amount") or 0.0)
    now = datetime.now(timezone.utc)
    batch_id = str(uuid4())
    batch = ClaimBatchRecord(
        batch_id=batch_id,
        batch_number=f"BNHAI-{now:%Y%m%d}-{uuid4().hex[:8].upper()}",
        facility_id=payload.facility_id,
        created_by=user.user_id,
        status="prepared",
        document_count=len(docs),
        total_amount=round(total, 2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.flush()
    for item in docs:
        item.batch_id = batch_id
        item.claim_status = "batched"
        item.updated_at = now
    notify_facility_roles(
        db,
        facility_id=payload.facility_id,
        roles={"facility_admin"},
        category="administration",
        title="Claim batch prepared",
        message=f"Claim batch {batch.batch_number} with {len(docs)} invoice(s) is ready for external submission review.",
        resource_type="claim_batches",
        resource_id=batch_id,
        exclude_user_id=user.user_id,
    )
    db.commit()
    db.refresh(batch)
    return _serialize_batch(batch)


@router.get("/batches", response_model=list[ClaimBatchRead], summary="List prepared claim batches")
def list_claim_batches(
    db: DbSession,
    user: CurrentUser,
    facility_id: str | None = None,
    limit: int = 50,
) -> list[ClaimBatchRead]:
    limit = max(1, min(limit, 200))
    allowed_facilities = assigned_facility_ids(user, CLAIM_READ_ROLES)
    if facility_id:
        if facility_id not in allowed_facilities:
            raise HTTPException(status_code=404, detail="Claim batches not found.")
        allowed_facilities = {facility_id}
    rows = db.scalars(
        select(ClaimBatchRecord)
        .where(ClaimBatchRecord.facility_id.in_(allowed_facilities))
        .order_by(ClaimBatchRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialize_batch(item) for item in rows]


@router.get("/batches/{batch_id}", response_model=ClaimBatchRead, summary="Read one claim batch")
def get_claim_batch(batch_id: str, db: DbSession, user: CurrentUser) -> ClaimBatchRead:
    return _serialize_batch(_get_batch(batch_id, db, user, CLAIM_READ_ROLES))


@router.post("/batches/{batch_id}/export-review-csv", summary="Download an internal review CSV (not a BPOMAS EDI file)")
def export_claim_batch_review_csv(batch_id: str, db: DbSession, user: CurrentUser) -> StreamingResponse:
    batch = _get_batch(batch_id, db, user, CLAIM_BATCH_ROLES)
    if batch.status not in {"prepared", "exported"}:
        raise HTTPException(status_code=409, detail="Only prepared batches can be exported for review.")
    docs = db.scalars(
        select(ClaimDocumentRecord)
        .where(ClaimDocumentRecord.batch_id == batch_id)
        .order_by(ClaimDocumentRecord.created_at)
    ).all()
    if not docs:
        raise HTTPException(status_code=409, detail="This batch contains no invoice documents.")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([
        "invoice_number", "member_surname_initials", "patient_first_name", "benefit_option",
        "membership_number", "practice_code", "practice_name", "provider_name", "service_date",
        "service_description", "diagnosis_code", "tariff_code", "quantity", "amount", "currency",
        "member_signature_confirmed", "provider_signature_confirmed", "referral_document_confirmed",
        "source_filename", "claim_document_id",
    ])
    for document in docs:
        fields = ClaimExtractedFields.model_validate(json.loads(document.extracted_fields_json or "{}"))
        row = fields.model_dump(mode="json")
        writer.writerow([
            row.get(key) for key in (
                "invoice_number", "member_surname_initials", "patient_first_name", "benefit_option",
                "membership_number", "practice_code", "practice_name", "provider_name", "service_date",
                "service_description", "diagnosis_code", "tariff_code", "quantity", "amount", "currency",
                "member_signature_confirmed", "provider_signature_confirmed", "referral_document_confirmed",
            )
        ] + [document.original_filename, document.claim_document_id])
    content = buffer.getvalue().encode("utf-8-sig")
    batch.status = "exported"
    batch.updated_at = datetime.now(timezone.utc)
    db.commit()
    filename = f"BNHAI_INTERNAL_REVIEW_ONLY_{batch.batch_number}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-BNHAI-Export-Warning": "INTERNAL REVIEW EXPORT ONLY. NOT A BPOMAS EDI, XML/MIP OR APPROVED CSV SUBMISSION FILE.",
        },
    )


@router.post("/batches/{batch_id}/record-external-submission", response_model=ClaimBatchRead, summary="Record a submission completed outside BNHAI")
def record_external_submission(
    batch_id: str,
    payload: ClaimBatchExternalSubmission,
    db: DbSession,
    user: CurrentUser,
) -> ClaimBatchRead:
    batch = _get_batch(batch_id, db, user, CLAIM_BATCH_ROLES)
    if batch.status != "exported":
        raise HTTPException(status_code=409, detail="Export the review batch first, then record an external submission.")
    batch.status = "submitted_externally"
    batch.external_submission_reference = payload.external_submission_reference
    batch.external_submission_channel = payload.external_submission_channel
    batch.external_submitted_at = datetime.now(timezone.utc)
    batch.acknowledgement_notes = payload.acknowledgement_notes
    batch.updated_at = datetime.now(timezone.utc)
    docs = db.scalars(select(ClaimDocumentRecord).where(ClaimDocumentRecord.batch_id == batch_id)).all()
    for document in docs:
        document.claim_status = "submitted_externally"
        document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(batch)
    return _serialize_batch(batch)


@router.post(
    "/batches/{batch_id}/record-acknowledgement",
    response_model=ClaimBatchRead,
    summary="Record an external BPOMAS acknowledgement manually",
)
def record_claim_batch_acknowledgement(
    batch_id: str,
    payload: ClaimBatchAcknowledgement,
    db: DbSession,
    user: CurrentUser,
) -> ClaimBatchRead:
    batch = _get_batch(batch_id, db, user, CLAIM_BATCH_ROLES)
    if batch.status != "submitted_externally":
        raise HTTPException(status_code=409, detail="Record the external submission first.")
    batch.status = "acknowledged" if payload.outcome == "accepted" else "rejected"
    batch.acknowledgement_notes = payload.notes
    batch.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(batch)
    return _serialize_batch(batch)
