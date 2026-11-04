"""Database engine and request-scoped SQLAlchemy sessions."""

import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}

_configured_database_url = os.getenv("DATABASE_URL")

if IS_PRODUCTION:
    if not _configured_database_url:
        raise RuntimeError(
            "DATABASE_URL must be set when APP_ENV is production."
        )

    database_url = make_url(_configured_database_url)

    if database_url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Production requires a PostgreSQL DATABASE_URL."
        )

DATABASE_URL = _configured_database_url or "sqlite:///./healthcare.db"

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(
        dbapi_connection,
        _connection_record,
    ) -> None:
        """Enforce foreign-key constraints in local SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per API request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
