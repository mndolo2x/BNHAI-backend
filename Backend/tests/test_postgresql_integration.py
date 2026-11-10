
"""PostgreSQL integration tests using a dedicated test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def pg_engine():
    url = os.getenv("BNHAI_TEST_DATABASE_URL")

    if not url:
        pytest.skip("BNHAI_TEST_DATABASE_URL is not configured")

    parsed = make_url(url)

    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "bnhai_test"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.port != 5432
        or parsed.username != "bnhai_test"
    ):
        pytest.fail("Unsafe PostgreSQL test database configuration")

    engine = create_engine(url, pool_pre_ping=True)

    try:
        yield engine
    finally:
        engine.dispose()


def test_postgresql_transaction_rollback(pg_engine):
    """Verify that rolling back a transaction removes its changes."""
    with pg_engine.connect() as connection:
        transaction = connection.begin()

        try:
            connection.execute(
                text(
                    "CREATE TEMP TABLE bnhai_rollback_test "
                    "(id INTEGER PRIMARY KEY, value TEXT) "
                    "ON COMMIT PRESERVE ROWS"
                )
            )

            connection.execute(
                text(
                    "INSERT INTO bnhai_rollback_test (id, value) "
                    "VALUES (1, 'temporary')"
                )
            )

            count = connection.scalar(
                text("SELECT COUNT(*) FROM bnhai_rollback_test")
            )
            assert count == 1
        finally:
            transaction.rollback()

        exists = connection.scalar(
            text(
                "SELECT to_regclass("
                "'pg_temp.bnhai_rollback_test')"
            )
        )
        assert exists is None


def test_postgresql_concurrent_updates(pg_engine):
    """Verify two concurrent increments are both preserved."""
    barrier = Barrier(2, timeout=10)

    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE bnhai_concurrency_test "
                "(id INTEGER PRIMARY KEY, counter INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO bnhai_concurrency_test "
                "(id, counter) VALUES (1, 0)"
            )
        )

    try:
        def increment():
            with pg_engine.begin() as connection:
                barrier.wait()
                connection.execute(
                    text(
                        "UPDATE bnhai_concurrency_test "
                        "SET counter = counter + 1 WHERE id = 1"
                    )
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(increment)
                for _ in range(2)
            ]
            for future in futures:
                future.result()

        with pg_engine.connect() as connection:
            result = connection.scalar(
                text(
                    "SELECT counter FROM bnhai_concurrency_test "
                    "WHERE id = 1"
                )
            )

        assert result == 2

    finally:
        with pg_engine.begin() as connection:
            connection.execute(
                text("DROP TABLE IF EXISTS bnhai_concurrency_test")
            )


def test_postgresql_patient_workspace_read_persists_audit(pg_engine):
    """Verify real patient workspace access and auditing in PostgreSQL."""
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import sessionmaker

    from app.auth.security import create_access_token, hash_password
    from app.db import models as _models  # noqa: F401
    from app.db.base import Base
    from app.db.models import (
        AuditEventRecord,
        UserFacilityRoleRecord,
        UserRecord,
    )
    from app.db.seed import seed_demo_patients
    from app.db.session import get_db
    from app.main import app

    schema = f"bnhai_ws_test_{uuid4().hex}"
    actor_id = "TEST-PG-CLINICIAN"

    with pg_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    isolated_engine = None
    had_override = get_db in app.dependency_overrides
    original_override = app.dependency_overrides.get(get_db)

    try:
        isolated_engine = create_engine(
            pg_engine.url,
            pool_pre_ping=True,
            connect_args={"options": f"-csearch_path={schema} -clock_timeout=1000ms"},
        )

        with isolated_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT current_schema()")
            ) == schema

        Base.metadata.create_all(bind=isolated_engine)

        PgSession = sessionmaker(
            bind=isolated_engine,
            autoflush=False,
            autocommit=False,
        )

        with PgSession() as db:
            seed_demo_patients(db)

            db.add(
                UserRecord(
                    user_id=actor_id,
                    username="test_pg_clinician",
                    display_name="Synthetic PostgreSQL Clinician",
                    password_hash=hash_password("TestPassword123!"),
                    is_active=True,
                )
            )
            db.flush()

            db.add(
                UserFacilityRoleRecord(
                    assignment_id="ASSIGNMENT-TEST-PG-CLINICIAN",
                    user_id=actor_id,
                    facility_id="DEMO-FACILITY-001",
                    role="clinician",
                )
            )
            db.commit()

        def override_get_db():
            with PgSession() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/patients/DEMO-0001/workspace",
                headers={
                    "Authorization": (
                        f"Bearer {create_access_token(actor_id)}"
                    )
                },
            )

            assert response.status_code == 200, response.text
            assert response.json()["patient"]["patient_id"] == "DEMO-0001"

            denied = client.get(
                "/api/v1/patients/DEMO-0003/workspace",
                headers={
                    "Authorization": f"Bearer {create_access_token(actor_id)}"
                },
            )
            assert denied.status_code == 404, denied.text
            assert "clinical_notes" not in denied.text

            # Launch six API requests at approximately the same time.
            concurrent_count = 6
            barrier = Barrier(concurrent_count, timeout=15)
            headers = {"Authorization": f"Bearer {create_access_token(actor_id)}"}

            def read_workspace(_index: int):
                barrier.wait()
                return client.get(
                    "/api/v1/patients/DEMO-0001/workspace",
                    headers=headers,
                )

            with ThreadPoolExecutor(max_workers=concurrent_count) as executor:
                responses = list(executor.map(read_workspace, range(concurrent_count)))

            statuses = [result.status_code for result in responses]
            assert statuses == [200] * concurrent_count, statuses
            assert all(
                result.json()["patient"]["patient_id"] == "DEMO-0001"
                for result in responses
            )

            # Block audit writes using a separate PostgreSQL transaction.
            with pg_engine.connect() as lock_connection:
                with lock_connection.begin():
                    lock_connection.execute(
                        text(
                            f'LOCK TABLE "{schema}".audit_events '
                            'IN ACCESS EXCLUSIVE MODE'
                        )
                    )

                    blocked = client.get(
                        "/api/v1/patients/DEMO-0001/workspace",
                        headers=headers,
                    )

                    assert blocked.status_code == 503, blocked.text
                    assert blocked.json() == {
                        "detail": "Patient workspace temporarily unavailable."
                    }
                    assert "DEMO-0001" not in blocked.text
                    assert "clinical_notes" not in blocked.text

        with PgSession() as db:
            events = db.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.actor_id == actor_id,
                    AuditEventRecord.action == "read",
                    AuditEventRecord.resource_type == "patients",
                    AuditEventRecord.resource_id == "DEMO-0001",
                    AuditEventRecord.outcome == "success",
                )
            ).all()

            expected_successful_reads = 1 + concurrent_count
            assert len(events) == expected_successful_reads, (
                f"Expected {expected_successful_reads} successful read audits, "
                f"got {len(events)}"
            )
            assert events[0].actor_source == "authenticated-user"
            assert events[0].occurred_at is not None

            denied_events = db.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.actor_id == actor_id,
                    AuditEventRecord.actor_source == "authenticated-user",
                    AuditEventRecord.action == "read",
                    AuditEventRecord.resource_type == "patients",
                    AuditEventRecord.resource_id == "DEMO-0003",
                    AuditEventRecord.outcome == "denied",
                )
            ).all()
            assert len(denied_events) == 1, (
                f"Expected one PostgreSQL denied-read audit, got {len(denied_events)}"
            )
            assert denied_events[0].occurred_at is not None

    finally:
        if had_override:
            app.dependency_overrides[get_db] = original_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if isolated_engine is not None:
            isolated_engine.dispose()

        with pg_engine.begin() as connection:
            connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            )
