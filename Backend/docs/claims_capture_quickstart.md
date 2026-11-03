# BNHAI Claims Capture v1 — local test walkthrough

**Use synthetic invoices only. Do not upload real member or patient information.**

This version supports individual and multi-file PDF uploads, text extraction from searchable PDFs, structured field parsing, basic completeness checks, human correction/approval, duplicate checks, batch preparation, an internal review CSV, and manual recording of an external submission/acknowledgement.

Scanned/image-only PDFs are saved and flagged `needs_ocr`. OCR is not enabled in this version. The module does not verify BPOMAS membership eligibility, benefit balances, tariff validity, ICD-10/tariff compatibility, signatures, or claim acceptance. It does not directly submit to BPOMAS.

## Install / migrate

From the existing `backend` folder in PowerShell, with its virtual environment active:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m alembic upgrade head
python -m alembic current
```

The expected migration head is `0007_claims_capture`. Uploaded PDFs are stored locally in `data/claims` by default. Override this location with `CLAIMS_STORAGE_DIR` before starting Uvicorn if required.

## Test an individual invoice or bulk upload

1. Start the API and open `http://127.0.0.1:8000/docs`.
2. Sign in using a facility-scoped receptionist, facility administrator, or platform administrator account, then use Swagger's **Authorize** button with the access token.
3. Open `POST /api/v1/claims/documents`.
4. Enter `facility_id` (for the demo data, `DEMO-FACILITY-001`).
5. Select one or more PDF files in `files`. For a bulk test, select several files in the same request.
6. Execute. The response separates `uploaded` documents from `rejected` files. Each uploaded document includes extracted fields, extraction status, claim status, missing fields, warnings and validation scope.

Limits: 20 MB per PDF, 60 pages per PDF, 100 PDFs per request and 100 MB total per bulk request. Only PDF files are accepted. Exact file duplicates are marked `duplicate`. Matching invoice/member keys in a different PDF are flagged as a possible duplicate and require human review.

## Correct extracted fields

Use `PATCH /api/v1/claims/documents/{document_id}` as a receptionist/facility administrator/platform administrator. Supply only the fields to correct inside `fields`, for example:

```json
{
  "fields": {
    "membership_number": "SAMPLE-MEMBER-0001",
    "member_signature_confirmed": true
  }
}
```

The example value above is synthetic. `member_signature_confirmed` must only be set after a human has visually checked the invoice. Do not set it based on text extraction alone.

## Approve and prepare a batch

A clinician, facility administrator or platform administrator can approve a completed invoice with `POST /api/v1/claims/documents/{document_id}/approve`:

```json
{
  "member_signature_confirmed": true,
  "provider_signature_confirmed": true,
  "referral_document_confirmed": true
}
```

These confirmation values are appropriate only for the synthetic test invoice supplied here. Real invoices require an actual human review of the source document and the applicable BPOMAS rules.

A facility administrator or platform administrator can prepare a batch with `POST /api/v1/claims/batches`:

```json
{
  "facility_id": "DEMO-FACILITY-001",
  "claim_document_ids": ["REPLACE-WITH-APPROVED-DOCUMENT-ID"]
}
```

Only approved documents from the same facility may be batched. The system prevents re-batching the same document.

## Export and external submission tracking

Use `POST /api/v1/claims/batches/{batch_id}/export-review-csv` to download the BNHAI internal review CSV. The filename contains `INTERNAL_REVIEW_ONLY`, and the response has an `X-BNHAI-Export-Warning` header.

**This CSV is not a BPOMAS EDI/XML/MIP or approved Botswana CSV submission file. Do not send it to BPOMAS as a claim batch.** Once BPOMAS confirms its current specification, a compliant exporter can be added separately.

After a staff member submits through an approved external BPOMAS channel, the external reference can be recorded with `POST /api/v1/claims/batches/{batch_id}/record-external-submission`. This endpoint only records a submission completed outside BNHAI; it does not send anything to BPOMAS. An external acknowledgement can be recorded with `POST /api/v1/claims/batches/{batch_id}/record-acknowledgement`.

## Roles

- Receptionist: upload, read and correct invoice fields; cannot approve or create batches.
- Clinician: read and approve invoices; cannot create batches.
- Facility administrator: upload, correct, approve, create/export batches and record external submission/acknowledgement within their facility.
- Platform administrator: same operations at facilities to which that account is assigned; no bypass of the facility assignment check is implemented here.
- Auditor: read claim capture records within assigned facilities.

## Important security limitations

The storage directory is local but **not encrypted at rest** in this development version. Do not use real data. Before a real pilot, add encrypted file storage, retention/deletion workflows, malware scanning, OCR with confidence thresholds, stronger operational audit controls, secure deployment, and an approved BPOMAS data-exchange agreement/specification. Confirm who may view, correct, approve and submit claims with each practice before production use.
