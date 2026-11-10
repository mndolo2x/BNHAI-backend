"""Read-only privilege verifier for BNHAI's isolated PostgreSQL test role."""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

EXPECTED_TABLES = {
    "alembic_version", "audit_events", "claim_batches",
    "claim_documents", "clinical_notes", "encounters",
    "facilities", "follow_up_tasks", "lab_observations",
    "lab_reports", "notifications", "patient_account_links",
    "patient_identity_verifications", "patients",
    "user_facility_roles", "users",
}

PRIVILEGES = (
    "SELECT", "INSERT", "UPDATE", "DELETE",
    "TRUNCATE", "REFERENCES", "TRIGGER",
)


def expected_privileges(table):
    if table == "alembic_version":
        return (False,) * len(PRIVILEGES)
    if table == "audit_events":
        return (True, True, False, False, False, False, False)
    return (True, True, True, True, False, False, False)


def main():
    raw = os.environ.get("BNHAI_TEST_RUNTIME_DATABASE_URL")
    if not raw:
        raise SystemExit("STOP: Test runtime database URL not set.")

    target = make_url(raw)
    if not (
        target.get_backend_name() == "postgresql"
        and target.username == "bnhai_app_runtime"
        and target.database == "bnhai_test"
        and target.host in ("localhost", "127.0.0.1")
        and target.port == 5432
        and target.password
    ):
        raise SystemExit("STOP: Unsafe PostgreSQL test target.")

    engine = create_engine(
        target,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    try:
        with engine.connect() as connection:
            identity = connection.execute(
                text("SELECT current_user, current_database()")
            ).one()

            if tuple(identity) != ("bnhai_app_runtime", "bnhai_test"):
                raise RuntimeError("Unexpected database identity.")

            flags = connection.execute(text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )).one()

            if tuple(flags) != (False, False, False, False):
                raise RuntimeError("Runtime account is privileged.")

            capabilities = connection.execute(text(
                "SELECT "
                "has_schema_privilege(current_user, 'public', 'USAGE'), "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "has_database_privilege("
                "current_user, current_database(), 'CREATE'), "
                "pg_has_role(current_user, 'bnhai_test', 'MEMBER')"
            )).one()

            if tuple(capabilities) != (True, False, False, False):
                raise RuntimeError("Unexpected schema or database privileges.")

            tables = [
                row[0] for row in connection.execute(text(
                    "SELECT tablename FROM pg_catalog.pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                ))
            ]

            if set(tables) != EXPECTED_TABLES:
                raise RuntimeError(
                    "Database schema differs from security baseline. "
                    f"Extra: {sorted(set(tables) - EXPECTED_TABLES)}; "
                    f"Missing: {sorted(EXPECTED_TABLES - set(tables))}"
                )

            for table in tables:
                actual = tuple(
                    connection.execute(
                        text(
                            "SELECT has_table_privilege("
                            "current_user, "
                            "format('%I.%I', 'public', CAST(:tablename AS text)), "
                            "CAST(:privilege AS text))"
                        ),
                        {
                            "tablename": table,
                            "privilege": privilege,
                        },
                    ).scalar_one()
                    for privilege in PRIVILEGES
                )

                expected = expected_privileges(table)

                if actual != expected:
                    differences = [
                        (privilege, received, required)
                        for privilege, received, required
                        in zip(PRIVILEGES, actual, expected)
                        if received != required
                    ]
                    raise RuntimeError(
                        f"Permission mismatch on {table}: {differences}"
                    )

        print("PASS: Runtime identity and role restrictions verified.")
        print("PASS: 14 application tables have restricted CRUD access.")
        print("PASS: Audit history allows SELECT and INSERT only.")
        print("PASS: Migration history and administration are restricted.")
        print("PASS: All 16 tables match the security baseline.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
