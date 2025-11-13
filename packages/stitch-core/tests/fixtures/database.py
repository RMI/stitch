"""Database fixtures for testing SQL adapters with SQLite in-memory database."""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from stitch.core.resources.adapters.sql.model.base import Base


@pytest.fixture(scope="function")
def db_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine for testing.

    Scope: function - Each test gets a fresh database.

    Yields:
        Engine: SQLAlchemy engine connected to in-memory SQLite database.
    """
    from sqlalchemy import event

    engine = create_engine("sqlite:///:memory:", echo=False)

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables defined in Base metadata
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: drop all tables
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Create a database session with automatic rollback.

    The session is configured to automatically rollback after each test,
    ensuring test isolation even if the test doesn't explicitly commit.

    Args:
        db_engine: The SQLite engine fixture.

    Yields:
        Session: SQLAlchemy session for database operations.
    """
    SessionFactory = sessionmaker(
        bind=db_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    session = SessionFactory()

    yield session

    # Rollback any uncommitted changes
    session.rollback()
    session.close()
