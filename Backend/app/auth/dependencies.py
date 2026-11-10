"""Request authentication and endpoint-level role authorization."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.models import UserFacilityRoleRecord, UserRecord
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class AssignedRole:
    facility_id: str
    role: str


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    display_name: str
    is_active: bool
    assignments: tuple[AssignedRole, ...]

    @property
    def role_names(self) -> set[str]:
        return {assignment.role for assignment in self.assignments}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> AuthenticatedUser:
    """Validate the bearer token and reload current active user/roles from the DB."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated or access token is invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise unauthorized

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise unauthorized from None

    user = db.get(UserRecord, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    assignments = db.scalars(
        select(UserFacilityRoleRecord)
        .where(UserFacilityRoleRecord.user_id == user.user_id)
        .order_by(UserFacilityRoleRecord.facility_id, UserFacilityRoleRecord.role)
    ).all()
    return AuthenticatedUser(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        assignments=tuple(
            AssignedRole(facility_id=item.facility_id, role=item.role)
            for item in assignments
        ),
    )


PATIENT_READ = {
    "receptionist", "nurse", "clinician", "laboratory_worker",
    "follow_up_worker", "facility_admin", "auditor", "platform_admin",
}

PATIENT_WRITE = {"receptionist", "facility_admin", "platform_admin"}

PATIENT_IDENTITY_VERIFY = {"receptionist", "facility_admin"}
PATIENT_IDENTITY_APPROVE = {"facility_admin"}

CLINICAL_READ = {"clinician", "nurse", "facility_admin", "auditor", "platform_admin"}

ENCOUNTER_WRITE = {"clinician", "nurse", "platform_admin"}
NOTE_WRITE = {"clinician", "platform_admin"}
LAB_READ = {
    "laboratory_worker", "clinician", "nurse", "follow_up_worker",
    "facility_admin", "auditor", "platform_admin",
}
LAB_WRITE = {"laboratory_worker", "facility_admin", "platform_admin"}
FOLLOW_UP_READ = {
    "follow_up_worker", "clinician", "nurse", "facility_admin", "auditor", "platform_admin",
}
FOLLOW_UP_WRITE = {
    "follow_up_worker", "nurse", "clinician", "facility_admin", "platform_admin",
}
AUDIT_READ = {"auditor", "facility_admin", "platform_admin"}
DASHBOARD_READ = PATIENT_READ | CLINICAL_READ | LAB_READ | FOLLOW_UP_READ | AUDIT_READ
NOTIFICATION_READ = {
    "receptionist", "nurse", "clinician", "laboratory_worker",
    "follow_up_worker", "facility_admin", "auditor", "platform_admin",
}
USER_ADMIN = {"facility_admin", "platform_admin"}
FACILITY_ADMIN_READ = {"facility_admin", "platform_admin"}
PLATFORM_ADMIN_ONLY = {"platform_admin"}


def required_roles_for_request(method: str, path: str) -> set[str] | None:
    """Map a known API operation to the roles permitted to invoke it.

    Returns None for an API operation without an explicit policy; these are
    denied by default rather than accidentally becoming public.
    """
    path = path.rstrip("/") or "/"
    method = method.upper()

    # Patient enrollment and identity verification API permissions.
    if path == "/api/v1/patient-links" and method == "POST":
        return PATIENT_WRITE

    if path.startswith("/api/v1/patient-links/") and method == "POST":
        parts = path.split("/")

        if len(parts) == 6 and parts[4]:
            if parts[5] == "verify-identity":
                return PATIENT_IDENTITY_VERIFY

            if parts[5] == "approve":
                return PATIENT_IDENTITY_APPROVE


    if path == "/api/v1/dashboard/summary" and method == "GET":
        return DASHBOARD_READ

    if path == "/api/v1/notifications":
        if method == "GET":
            return NOTIFICATION_READ
    if path.startswith("/api/v1/notifications/") and method in {"PATCH", "POST"}:
        return NOTIFICATION_READ

    if path == "/api/v1/admin/users":
        if method in {"GET", "POST"}:
            return USER_ADMIN
    if path.startswith("/api/v1/admin/users/"):
        if method == "PATCH" and "/assignments" not in path:
            return PLATFORM_ADMIN_ONLY
        if method == "POST" and path.endswith("/assignments"):
            return USER_ADMIN
        if method == "DELETE" and "/assignments/" in path:
            return USER_ADMIN

    if path == "/api/v1/facilities":
        if method == "GET":
            return FACILITY_ADMIN_READ
        if method == "POST":
            return PLATFORM_ADMIN_ONLY
    if path.startswith("/api/v1/facilities/") and method == "PATCH":
        return PLATFORM_ADMIN_ONLY

    # The consolidated patient workspace includes clinical notes, lab reports, and
    # follow-up tasks, so it requires a clinical-read role, not just directory access.
    if path.startswith("/api/v1/patients/") and path.endswith("/workspace") and method == "GET":
        return CLINICAL_READ

    if path == "/api/v1/patients" or path.startswith("/api/v1/patients/"):
        if method == "GET":
            return PATIENT_READ
        if method == "POST" and path == "/api/v1/patients":
            return PATIENT_WRITE

    if path.startswith("/api/v1/encounters"):
        if "/notes" in path:
            if method == "GET":
                return CLINICAL_READ
            if method in {"POST", "PATCH"}:
                return NOTE_WRITE
        if method == "GET":
            return CLINICAL_READ
        if method == "POST":
            return ENCOUNTER_WRITE
        if method == "PATCH":
            return ENCOUNTER_WRITE

    if path.startswith("/api/v1/notes/"):
        if method == "GET":
            return CLINICAL_READ
        if method in {"PATCH", "POST"}:
            return NOTE_WRITE

    if path.startswith("/api/v1/lab-results"):
        if method == "GET":
            return LAB_READ
        if method in {"POST", "PATCH"}:
            return LAB_WRITE

    if path.startswith("/api/v1/follow-ups"):
        if method == "GET":
            return FOLLOW_UP_READ
        if method in {"POST", "PATCH"}:
            return FOLLOW_UP_WRITE

    if path == "/api/v1/audit-events" and method == "GET":
        return AUDIT_READ

    if path.startswith("/api/v1/claims"):
        claim_read = {"receptionist", "clinician", "nurse", "facility_admin", "auditor", "platform_admin"}
        claim_upload = {"receptionist", "facility_admin", "platform_admin"}
        claim_review = {"clinician", "facility_admin", "platform_admin"}
        claim_batch = {"facility_admin", "platform_admin"}
        if method == "GET":
            return claim_read
        if path == "/api/v1/claims/documents" and method == "POST":
            return claim_upload
        if path.startswith("/api/v1/claims/documents/"):
            if method == "GET":
                return claim_read
            if method == "PATCH":
                return claim_upload
            if method == "POST" and path.endswith("/approve"):
                return claim_review
        if path.startswith("/api/v1/claims/batches") and method == "POST":
            if path == "/api/v1/claims/batches":
                return claim_batch
            if (
                path.endswith("/export-review-csv")
                or path.endswith("/record-external-submission")
                or path.endswith("/record-acknowledgement")
            ):
                return claim_batch

    return None


def authorize_api_request(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbSession,
) -> None:
    """Require an allowed role for every API route using this dependency."""
    required = required_roles_for_request(request.method, request.url.path)
    if required is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No authorization policy is defined for this operation.",
        )
    if not (current_user.role_names & required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your assigned role does not permit this operation.",
        )

    # The audit listener uses the same request-scoped Session to attribute mutations.
    db.info["audit_actor_id"] = current_user.user_id
    db.info["audit_actor_source"] = "authenticated-user"
