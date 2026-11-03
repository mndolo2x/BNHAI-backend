"""Safe, repeatable insertion of synthetic starter records for local development."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.demo_patients import DEMO_PATIENTS
from app.db.models import FacilityRecord, PatientRecord


def seed_demo_patients(db: Session) -> int:
    """Seed demo patients only when the patients table is empty.

    Returns the number of inserted records. Does not overwrite existing data.
    """
    # Keep a managed facility directory in sync with the synthetic patient fixtures.
    # This matters for brand-new databases where migrations run before demo seeding.
    facility_names = {
        "DEMO-FACILITY-001": "Demo Facility 001",
        "DEMO-FACILITY-002": "Demo Facility 002",
    }
    for facility_id, name in facility_names.items():
        if db.get(FacilityRecord, facility_id) is None:
            db.add(FacilityRecord(facility_id=facility_id, name=name))
    db.flush()

    existing_count = db.scalar(select(func.count()).select_from(PatientRecord)) or 0
    if existing_count > 0:
        db.commit()
        return 0

    records = [PatientRecord(**patient.model_dump(mode="python")) for patient in DEMO_PATIENTS]
    db.add_all(records)
    db.commit()
    return len(records)
