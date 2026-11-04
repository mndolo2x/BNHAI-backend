
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