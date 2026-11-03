"""Seed the local database with fictional starter records.

Run after `python -m alembic upgrade head` from the backend directory.
"""
from sqlalchemy.orm import Session

from app.db.seed import seed_demo_patients
from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:  # type: Session
        inserted = seed_demo_patients(db)
        if inserted:
            print(f"Inserted {inserted} synthetic demo patients.")
        else:
            print("Demo records were not added because the patients table is not empty.")


if __name__ == "__main__":
    main()
