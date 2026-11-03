# Botswana National Healthcare AI Platform — Backend Milestone 11 + Claims Capture v1

Development API for synthetic data only. This is not approved for real patient data and is not connected to Botswana's national health systems.

## Included

- Database-backed patients, encounters, clinical-note drafts/versions, laboratory reports/observations, and follow-up tasks.
- Alembic migrations through `0007_claims_capture` (facility directory, notifications, invoice capture and claim batches).
- Development audit events for successful ORM database mutations (create/update/delete).
- Read-only API listing for audit metadata with filters and a bounded limit.
- Local authentication, endpoint-level role authorization, and facility-scoped access checks.
- Read-only patient workspace endpoint consolidating patient demographics, encounters, clinical notes, lab reports, and follow-up tasks.
- Live, role-filtered dashboard metrics and scoped recent activity.
- User-specific notification inbox, read/unread state, and automatic workflow notifications for new lab reports, notes submitted for review, and follow-up tasks.
- Managed facility directory and role-aware user administration. Facility administrators manage staff roles at their own facilities; platform administrators manage users and the facility directory globally.
- Local BPOMAS invoice capture v1: single and bulk searchable-PDF upload, field extraction, basic completeness checks, exact/business-key duplicate flags, human corrections and approval, claim batch preparation, internal review CSV export, and manual external-submission/acknowledgement tracking.
- Read and write access is checked against the combination of the user's role and facility assignment.
- Automated tests using isolated SQLite databases, including cross-facility isolation cases.

## Important security limitations

Facility scoping is enforced in application/API handlers; this is not database-native row-level security and has not been independently security-certified. All users should be tested against their exact real-world permission matrix before any pilot.

The audit module records metadata for successful database mutations only. It does not yet audit reads, failed requests, or denied access. The audit log is not tamper-resistant and deliberately does not store clinical field contents. Clinical note approval is simulated. Do not use real patient data or expose this development API to a network.

MFA, password reset, refresh-token rotation, token revocation, rate limiting, and external identity-provider integration are not implemented. Facility assignments do not model cross-facility transfers, referrals, temporary access, emergency access, or break-glass workflows.

## Setup on Windows / PowerShell

Open this `backend` folder in VS Code, then create and activate a virtual environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

If `.venv` already exists and is using the intended Python interpreter, activate it instead of recreating it.

Run tests:

```powershell
python -m pytest -q
```

Apply database migrations:

```powershell
python -m alembic upgrade head
```

Start development server:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API documentation.

## Audit endpoint

`GET /api/v1/audit-events` supports `action`, `resource_type`, `resource_id`, and `limit` (1–100). It requires an authenticated `auditor`, `facility_admin`, or `platform_admin` role at a facility. Events are filtered to resources that can be tied to those assigned facilities. This local implementation is not production-ready.

## Milestone 7: local authentication and endpoint roles

This milestone added local development login using Argon2 password hashes and short-lived JWT bearer tokens. It adds `users` and `user_facility_roles` using the `0005_users_roles` Alembic migration, plus these endpoints:

- `POST /api/v1/auth/login` — exchange a username/password JSON body for a bearer token.
- `GET /api/v1/auth/me` — return the authenticated user's profile and role assignments.

Clinical/resource APIs require a bearer token and an explicit endpoint-role policy. Audit events now record the authenticated user ID for successful changes made in an authenticated API request.

## Milestone 8: facility-scoped authorization

This milestone makes access depend on both the user's assigned role and the facility linked to a record.

- Patient-directory lists are filtered by the facilities where the user has an allowed patient-directory role. Direct lookups hide out-of-scope patient records with `404`.
- Encounter lists and direct lookups are scoped to facilities where the user has a clinical-read role. Writes require an encounter-write role at the same facility.
- Clinical notes inherit scope from their encounter. Notes cannot be read or changed by a user whose required role is assigned only at another facility.
- Laboratory reports and follow-up tasks inherit facility scope from the linked patient and validate associated records.
- Audit-event listings expose only events that can be tied to a facility where the user has an audit-read role.
- A role at Facility 1 does not grant clinical access to Facility 2 just because the same user has some other role at Facility 2.

Resources outside the user's role/facility scope generally return `404` so the API does not confirm that those records exist. Attempts to write to a facility without the required role return `403`.

### Seed users and local login

If you have already run the Milestone 7 setup, you do **not** need to reseed users or replace your database. Existing accounts and their saved passwords stay in place. From the `backend` folder, with your virtual environment active:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m alembic upgrade head
```

Start the server with:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Use `POST /api/v1/auth/login` with the generated username and saved password. Copy `access_token`, click **Authorize**, and paste the token (without adding `Bearer` if Swagger's HTTP Bearer dialog asks for only the token).

### JWT secret for local development

If `JWT_SECRET_KEY` is not configured in development, the app creates a temporary random key when it starts; tokens become invalid when the server restarts. To keep tokens valid across restarts, set an environment variable in the same PowerShell terminal before starting Uvicorn, for example:

```powershell
$env:JWT_SECRET_KEY = "replace-this-with-a-random-secret-at-least-32-characters-long"
```

Use a unique random value locally; do not commit the real value to source control. The application refuses to start with `APP_ENV=production` if `JWT_SECRET_KEY` is missing.

## Milestone 11: operational backend APIs

This milestone adds the first operational services needed by the dashboard and administration screens.

### Dashboard

- `GET /api/v1/dashboard/summary` returns facility count, patient totals, active patients, encounters in progress, notes awaiting review, laboratory reports awaiting review, open follow-ups, overdue follow-ups, and recent in-scope audit activity.
- Each metric is calculated only over facilities and resource categories the current user's roles permit. A receptionist, for example, receives patient-directory metrics but not clinical, laboratory, or follow-up counts.
- Recent activity is metadata-only and is shown only when the user has audit-read access.

### Notifications

- `GET /api/v1/notifications` returns only the authenticated user's inbox. Supports `unread_only` and a bounded `limit`.
- `PATCH /api/v1/notifications/{notification_id}/read` marks one of the recipient's notifications as read.
- `POST /api/v1/notifications/read-all` marks all of the current user's unread notifications as read.
- New notifications are generated for authorised facility staff when a laboratory report is registered, a note is submitted for review, or a follow-up task is created. Messages deliberately contain workflow metadata only, not patient names, diagnoses, test values, or other clinical details.

### User administration

- `GET /api/v1/admin/users` lists users with assignments in facilities the caller manages; supports `facility_id` and `search`.
- `POST /api/v1/admin/users` creates a local user and an initial facility-role assignment. Passwords are hashed with Argon2 and never returned.
- `PATCH /api/v1/admin/users/{user_id}` changes display name and/or account active state; this global account operation is platform-administrator-only.
- `POST /api/v1/admin/users/{user_id}/assignments` assigns an additional role at a managed facility.
- `DELETE /api/v1/admin/users/{user_id}/assignments/{assignment_id}` removes a role assignment at a managed facility.
- Facility administrators can create staff and manage non-privileged roles only within their own facilities. They cannot grant `facility_admin` or `platform_admin` roles. Only platform administrators can grant privileged roles or change global account active state. The API prevents deactivation/removal of the last active platform administrator.

### Facilities

- `GET /api/v1/facilities` lists facilities visible to the current facility/platform administrator.
- `POST /api/v1/facilities` creates a facility (platform administrator only).
- `PATCH /api/v1/facilities/{facility_id}` updates directory details (platform administrator only).
- Migration `0006_operational` creates the facility and notification tables and backfills facility directory entries from existing patient, encounter, and role-assignment records. The synthetic data seeder also ensures the two demo facility records exist on a new installation.

These APIs are development foundations. They are not a replacement for a complete production identity lifecycle, enterprise audit platform, email/SMS/WhatsApp delivery service, real-time push channel, or operational monitoring stack.

## Development safety

Use synthetic data only. Keep the server bound to `127.0.0.1`; do not expose it to a network. This is still a learning prototype, not production healthcare infrastructure.

## Milestone 9: consolidated patient workspace

`GET /api/v1/patients/{patient_id}/workspace` returns one read-only object containing:

- `patient`: the patient-directory record.
- `encounters`: encounters linked to that patient and facility.
- `clinical_notes`: note versions linked through the scoped encounters.
- `lab_reports`: laboratory reports and their observations linked to the patient.
- `follow_up_tasks`: follow-up tasks linked to the patient and to records included in the response.

The endpoint requires a clinical-read role at the patient's assigned facility. Other facility users do not see the workspace; the endpoint returns `404` for missing or out-of-scope patient IDs. Users with directory-only permissions, such as a receptionist, receive `403`. This API is read-only and does not generate clinical interpretation, diagnosis, or treatment recommendations. Continue using synthetic data only.

## BPOMAS invoice capture (development v1)

The claims capture module accepts one or multiple PDF invoices at `POST /api/v1/claims/documents`.
Text-based PDFs are parsed with pypdf into reviewable fields. Scanned/image-only PDFs are retained and marked `needs_ocr`; OCR is not yet enabled in this release. Staff can correct extracted fields, and an authorised clinician or facility administrator must approve the invoice after confirming the member/dependant acknowledgement signature.

Approved invoices can be grouped into a batch. `POST /api/v1/claims/batches/{batch_id}/export-review-csv` downloads a BNHAI internal review CSV. **This export is not a BPOMAS EDI/XML/MIP or approved CSV submission file.** Direct BPOMAS submission is not implemented. `POST /api/v1/claims/batches/{batch_id}/record-external-submission` only records that a staff member submitted the batch separately and supplies an external reference.

Uploaded PDFs are stored locally under `CLAIMS_STORAGE_DIR` (default `./data/claims`). This prototype storage is not encrypted at rest. Use synthetic invoice data only. Before real deployment, configure encrypted storage/backups, access controls, retention rules, malware scanning, OCR review, and obtain current BPOMAS technical specifications and approved submission credentials/formats.


## BPOMAS claims capture v1 — endpoints

- `POST /api/v1/claims/documents` accepts one or many PDF invoices using multipart form fields `facility_id` and `files`. Text-based PDFs are parsed with pypdf. Image-only/scanned PDFs are stored and marked `needs_ocr`; OCR is not available in v1.
- `GET /api/v1/claims/documents` lists claim documents only for facilities where the current user has a claims-read role.
- `GET /api/v1/claims/documents/{id}` returns extracted fields and validation warnings. `GET /api/v1/claims/documents/{id}/file` downloads the original PDF under the same facility-scope check.
- `PATCH /api/v1/claims/documents/{id}` lets an authorised receptionist/facility administrator correct extracted fields.
- `POST /api/v1/claims/documents/{id}/approve` requires clinician, facility administrator or platform administrator permissions and an explicit human confirmation of the member/dependant acknowledgement signature.
- `POST /api/v1/claims/batches` groups approved documents from one authorised facility. `GET /api/v1/claims/batches` and `GET /api/v1/claims/batches/{id}` list and inspect batches.
- `POST /api/v1/claims/batches/{id}/export-review-csv` produces a BNHAI internal review CSV. It is **not** a BPOMAS EDI/XML/MIP or approved Botswana CSV submission file.
- `POST /api/v1/claims/batches/{id}/record-external-submission` records a submission completed by staff outside BNHAI. `POST /api/v1/claims/batches/{id}/record-acknowledgement` records a manually received acceptance/rejection. Neither endpoint transmits data to BPOMAS.

The parser is label-based and deliberately conservative. Required completeness fields include member surname/initials, patient first name, benefit option, membership number, practice code/name, service date, service description, diagnosis code, tariff code and amount. No member-number format, benefit balance, tariff validity, ICD-10/tariff compatibility, signature validity, or eligibility rule is inferred. Rules must be configured from current authorised BPOMAS technical guidance.

Bulk upload limits are 100 files per request, 20 MB per file, 60 pages per PDF, and 100 MB total. Exact PDF duplicates are flagged. Matching invoice/member details in a different PDF are marked as a **possible duplicate** warning for human comparison, not automatically rejected.

See `docs/claims_capture_quickstart.md` and `examples/synthetic_invoice_for_testing.pdf` for the development workflow. Claims PDFs are stored locally under `CLAIMS_STORAGE_DIR` (default `./data/claims`). This storage is not encrypted at rest in v1. Use synthetic data only.
