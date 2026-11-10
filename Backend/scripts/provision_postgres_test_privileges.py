"""Provision restricted permissions for the local BNHAI test database only.

Default: read-only preflight. --apply: atomically reapply permissions.
Not intended for production deployment.
"""

import argparse
from pathlib import Path

import psycopg
from psycopg import sql

DB = "bnhai_test"
ADMIN = "bnhai_test"
ROLE = "bnhai_app_runtime"

TABLES = {
    "alembic_version", "audit_events", "claim_batches",
    "claim_documents", "clinical_notes", "encounters",
    "facilities", "follow_up_tasks", "lab_observations",
    "lab_reports", "notifications", "patient_account_links",
    "patient_identity_verifications", "patients",
    "user_facility_roles", "users",
}

APP_TABLES = sorted(TABLES - {"alembic_version", "audit_events"})
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    secret_file = (
        Path.home() / ".config" / "bnhai" / "postgres-test.env"
    )

    if not secret_file.is_file():
        raise SystemExit("STOP: Test administrator credentials missing.")

    credentials = dict(
        line.split("=", 1)
        for line in secret_file.read_text().splitlines()
        if "=" in line
    )

    if (
        credentials.get("POSTGRES_USER") != ADMIN
        or credentials.get("POSTGRES_DB") != DB
        or not credentials.get("POSTGRES_PASSWORD")
    ):
        raise SystemExit("STOP: Unexpected administrator credentials.")

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=DB,
        user=ADMIN,
        password=credentials["POSTGRES_PASSWORD"],
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            if cursor.fetchone() != (DB, ADMIN):
                raise SystemExit("STOP: Unexpected database identity.")

            cursor.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, "
                "rolbypassrls, rolcanlogin, rolinherit "
                "FROM pg_roles WHERE rolname = %s",
                (ROLE,),
            )
            if cursor.fetchone() != (
                False, False, False, False, True, False
            ):
                raise SystemExit("STOP: Runtime role is missing or unsafe.")

            cursor.execute(
                "SELECT tablename, tableowner "
                "FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public'"
            )
            owners = dict(cursor.fetchall())

            if set(owners) != TABLES:
                raise SystemExit("STOP: Unexpected database table list.")

            if set(owners.values()) != {ADMIN}:
                raise SystemExit("STOP: Unexpected table ownership.")

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.sequences "
                "WHERE sequence_schema = 'public'"
            )
            if cursor.fetchone()[0] != 0:
                raise SystemExit(
                    "STOP: Database sequences require separate grants."
                )

            cursor.execute(
                "SELECT pg_has_role(%s, %s, 'MEMBER')",
                (ROLE, ADMIN),
            )
            if cursor.fetchone()[0]:
                raise SystemExit(
                    "STOP: Runtime belongs to administrator role."
                )

            print("PASS: Test database safety checks completed.")

            if not args.apply:
                print("DRY RUN: No permissions changed.")
                print("Ready to reapply the verified permission matrix.")
                return

            # All changes occur in one PostgreSQL transaction.
            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}"
                ).format(sql.Identifier(DB), sql.Identifier(ROLE))
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(DB), sql.Identifier(ROLE)
                )
            )

            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}"
                ).format(sql.Identifier(ROLE))
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(ROLE)
                )
            )

            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON ALL TABLES "
                    "IN SCHEMA public FROM {}"
                ).format(sql.Identifier(ROLE))
            )

            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON TABLE {} TO {}"
                ).format(
                    sql.SQL(", ").join(
                        sql.Identifier("public", name)
                        for name in APP_TABLES
                    ),
                    sql.Identifier(ROLE),
                )
            )

            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT "
                    "ON TABLE public.audit_events TO {}"
                ).format(sql.Identifier(ROLE))
            )

            # Verify effective permissions before committing.
            for table in sorted(TABLES):
                actual = tuple(
                    cursor.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (ROLE, f"public.{table}", privilege),
                    ).fetchone()[0]
                    for privilege in PRIVILEGES
                )

                if actual != expected_privileges(table):
                    raise RuntimeError(
                        f"STOP: Unexpected permissions for {table}."
                    )

    print("PASS: Restricted permissions applied atomically.")
    print("PASS: All 16 table permission sets verified.")


if __name__ == "__main__":
    main()
