"""FastAPI entry point for the Botswana National Healthcare AI Platform."""
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import authorize_api_request
from app.auth.router import router as auth_router
from app.api.v1.patient_portal import router as patient_portal_router
from app.api.v1.patient_links import router as patient_links_router
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

app.include_router(auth_router, prefix="/api/v1")
app.include_router(patient_portal_router, prefix="/api/v1")

protected_dependencies = [Depends(authorize_api_request)]
app.include_router(
    patient_links_router,
    prefix="/api/v1",
    dependencies=protected_dependencies,
)
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
