"""FastAPI entry point for the Botswana National Healthcare AI Platform."""
from typing import Annotated
import os

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from fastapi import Depends, FastAPI, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import authorize_api_request
from app.auth.router import router as auth_router
from app.api.v1.patients import router as patients_router
from app.api.v1.patient_workspace import router as patient_workspace_router
from app.api.v1.encounters import router as encounters_router
from app.api.v1.clinical_notes import router as clinical_notes_router
from app.api.v1.lab_results import router as lab_results_router
from app.api.v1.followups import router as followups_router
from app.api.v1.audit_events import router as audit_events_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.administration import router as administration_router
from app.api.v1.claims import router as claims_router
from app.db import audit as _audit  # noqa: F401 - registers ORM audit listener
from app.db.session import get_db

app = FastAPI(
    title="Botswana National Healthcare AI Platform API",
    description=(
        "Development API using synthetic patient records only. "
        "It is not connected to a national healthcare system. "
        "Local token authentication and role/facility authorization are implemented for prototype testing. "
        "Clinical note approval is simulated. Audit events cover successful database mutations only "
        "and are not a production security audit trail. Do not use real patient data."
    ),
    version="0.9.0",
    docs_url="/docs",
    redoc_url=None,
)
# Shared rate limiter for API endpoints.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

# Only explicitly configured frontend origins may access the API.
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Restrict accepted hostnames in production.
app_env = os.getenv("APP_ENV", "development").strip().lower()

allowed_hosts = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

if app_env in {"production", "prod"}:
    if not allowed_hosts or "*" in allowed_hosts:
        raise RuntimeError(
            "Production requires explicit ALLOWED_HOSTS without wildcards."
        )
else:
    allowed_hosts = allowed_hosts or [
        "localhost",
        "127.0.0.1",
        "testserver",
    ]

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts,
)

# Redirect HTTP requests to HTTPS in production.
# The deployment proxy must correctly communicate the original
# request scheme through trusted proxy configuration.
if app_env in {"production", "prod"}:
    app.add_middleware(HTTPSRedirectMiddleware)


app.include_router(auth_router, prefix="/api/v1")
# All clinical/resource APIs require a valid token and an explicitly allowed role.
protected_dependencies = [Depends(authorize_api_request)]
app.include_router(patients_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(patient_workspace_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(encounters_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(clinical_notes_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(lab_results_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(followups_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(audit_events_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(dashboard_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(notifications_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(administration_router, prefix="/api/v1", dependencies=protected_dependencies)
app.include_router(claims_router, prefix="/api/v1", dependencies=protected_dependencies)


@app.get("/health/live", tags=["Health"], summary="Check whether the API process is responding")
def health_live() -> dict[str, str]:
    """Return a liveness response without checking database readiness."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"], summary="Check whether the API can reach its configured database")
def health_ready(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Return ready only if a basic database query succeeds."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database is unavailable") from error
    return {"status": "ready", "database": "ok"}
