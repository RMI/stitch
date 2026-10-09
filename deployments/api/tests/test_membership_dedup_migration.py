"""Runs revision 901d261fce8b against a real (SQLite) database.

The rest of the suite builds its schema with ``metadata.create_all``, so it never
executes migrations. This revision deletes rows, so its keep-rule is exercised
here directly: upgrade to the previous head, insert duplicate memberships, then
upgrade and check which rows survive.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

ALEMBIC_DIR = Path(__file__).parents[1] / "alembic"
BEFORE = "71aa7ef8150b"
DEDUP = "901d261fce8b"


def _upgrade(connection: Connection, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    # env.py runs against a caller-supplied connection when one is given.
    config.attributes["connection"] = connection
    command.upgrade(config, revision)
    connection.commit()


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[Connection]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")
    with engine.connect() as conn:
        _upgrade(conn, BEFORE)
        yield conn
    engine.dispose()


def _insert(connection: Connection, sql: str, **params) -> int:
    return connection.execute(text(sql + " RETURNING id"), params).scalar_one()


def _insert_membership(
    connection: Connection, user_id: int, resource_id: int, source_pk: int, status: str
) -> int:
    return _insert(
        connection,
        "INSERT INTO og_field_memberships "
        "(resource_id, source, source_pk, status, created_by_id, last_updated_by_id) "
        "VALUES (:resource_id, 'gem', :source_pk, :status, :user_id, :user_id)",
        resource_id=resource_id,
        source_pk=source_pk,
        status=status,
        user_id=user_id,
    )


def test_dedup_keeps_active_else_lowest_id_then_enforces_uniqueness(
    connection: Connection,
):
    user_id = _insert(connection, "INSERT INTO users (sub) VALUES ('migration-test')")
    resources = [
        _insert(
            connection,
            "INSERT INTO og_field_resources (created_by_id, last_updated_by_id) "
            "VALUES (:u, :u)",
            u=user_id,
        )
        for _ in range(4)
    ]
    sources = [
        _insert(
            connection,
            "INSERT INTO oil_gas_field_sources "
            "(source, source_record, created_by_id, last_updated_by_id) "
            "VALUES ('gem', '{}', :u, :u)",
            u=user_id,
        )
        for _ in range(5)
    ]
    r1, r2, r3, r4 = resources
    s1, s2, s3, s4, s5 = sources

    # (resource, source, status, kept?) inserted in order, so ids ascend.
    cases = [
        # two ACTIVE: the lowest id is kept
        (r1, s1, "ACTIVE", True),
        (r1, s1, "ACTIVE", False),
        # ACTIVE beats a lower-id non-ACTIVE row
        (r1, s2, "INACTIVE", False),
        (r1, s2, "ACTIVE", True),
        # no ACTIVE row: the lowest id is kept, whatever its status
        (r2, s3, "INACTIVE", True),
        (r2, s3, "INVALID", False),
        # three rows: the first ACTIVE one is kept
        (r2, s4, "INACTIVE", False),
        (r2, s4, "ACTIVE", True),
        (r2, s4, "ACTIVE", False),
        # the same source on a different resource is not a duplicate
        (r3, s1, "ACTIVE", True),
        # a lone row is untouched, whatever its status
        (r4, s5, "INVALID", True),
    ]
    inserted = [
        (_insert_membership(connection, user_id, res, src, status), kept)
        for res, src, status, kept in cases
    ]
    connection.commit()

    _upgrade(connection, DEDUP)

    remaining = set(
        connection.execute(text("SELECT id FROM og_field_memberships")).scalars()
    )
    assert remaining == {mid for mid, kept in inserted if kept}

    unique_constraints = inspect(connection).get_unique_constraints(
        "og_field_memberships"
    )
    assert {
        "name": "uq_membership_resource_source",
        "column_names": ["resource_id", "source_pk"],
    } in [
        {"name": uc["name"], "column_names": uc["column_names"]}
        for uc in unique_constraints
    ]
    with pytest.raises(IntegrityError):
        _insert_membership(connection, user_id, r1, s1, "INACTIVE")
