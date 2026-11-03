"""Fictional patient records for local development and tests only."""

from app.models.patient import Patient, PatientStatus


DEMO_PATIENTS: list[Patient] = [
    Patient(
        patient_id="DEMO-0001",
        display_name="Demo Patient A",
        date_of_birth="1991-04-12",
        record_status=PatientStatus.active,
        facility_id="DEMO-FACILITY-001",
    ),
    Patient(
        patient_id="DEMO-0002",
        display_name="Demo Patient B",
        date_of_birth="1984-09-23",
        record_status=PatientStatus.active,
        facility_id="DEMO-FACILITY-001",
    ),
    Patient(
        patient_id="DEMO-0003",
        display_name="Demo Patient C",
        date_of_birth="2002-01-30",
        record_status=PatientStatus.inactive,
        facility_id="DEMO-FACILITY-002",
    ),
]
