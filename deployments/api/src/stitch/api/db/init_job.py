from __future__ import annotations

import os
import sys
import time
import logging
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
import hashlib
import json
from sqlalchemy.sql.schema import Column

from stitch.api.db.model import (
    StitchBase,
    create_coalesced_view,
)

logger = logging.getLogger("db-init")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


"""
DB init job.

This module is intended to be run as a one-shot job (e.g. a `db-init` service)
*before* the API starts. It can:
  - create schema from SQLAlchemy metadata if the DB is empty
  - fail fast on partial/mismatched schemas (no auto-healing)

Role separation / env vars:
  - The recommended setup uses two Postgres roles:
      * migrator role: DDL (used by the init job)
      * app role: no DDL (used by the API)
  - Set STITCH_DB_USER / STITCH_DB_PASSWORD on a per-service basis to choose
    which role connects (migrator for `db-init`, app for `api`).
  - POSTGRES_* variables are supported as a fallback for local convenience and
    backwards compatibility.
"""

META_SCHEMA_TABLE = "stitch_schema_meta"


class SchemaMode(str, Enum):
    IF_EMPTY = "if-empty"
    ASSERT_ONLY = "assert-only"
    NEVER = "never"


@dataclass(frozen=True)
class Settings:
    schema_mode: SchemaMode
    connect_timeout_s: int
    connect_retry_interval_s: float
    database_url: str


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return default if v is None else v


def build_db_url() -> str:
    """
    Prefer DATABASE_URL. Otherwise build from env vars.

    Recommended: use STITCH_DB_USER/STITCH_DB_PASSWORD to select the connecting
    role per service (migrator for db-init, app for api). POSTGRES_USER/
    POSTGRES_PASSWORD are supported as a fallback.
    """
    url = _env("DATABASE_URL")
    if url:
        return url

    host = _env("POSTGRES_HOST", "db")
    port = _env("POSTGRES_PORT", "5432")
    db = _env("POSTGRES_DB", "stitch")

    user = _env("STITCH_DB_USER", _env("POSTGRES_USER", "postgres"))
    pw = _env("STITCH_DB_PASSWORD", _env("POSTGRES_PASSWORD", "postgres"))

    # Works with SQLAlchemy+psycopg (v3).
    return f"postgresql+psycopg://{user}:{pw}@{host}:{port}/{db}"


def load_settings() -> Settings:
    return Settings(
        schema_mode=SchemaMode(
            _env("STITCH_DB_SCHEMA_MODE", SchemaMode.IF_EMPTY.value)
        ),
        connect_timeout_s=int(_env("STITCH_DB_CONNECT_TIMEOUT_S", "60")),
        connect_retry_interval_s=float(
            _env("STITCH_DB_CONNECT_RETRY_INTERVAL_S", "1.0")
        ),
        database_url=build_db_url(),
    )


def wait_for_db(engine, timeout_s: int, interval_s: float) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as e:
            last_err = e
            time.sleep(interval_s)
    raise RuntimeError(f"DB not reachable within {timeout_s}s. Last error: {last_err}")


def acquire_lock(conn) -> None:
    """
    Acquire an advisory lock on the given *open* SQLAlchemy Connection.
    The connection must remain open for the lock to be held.
    """
    conn.execute(text("SELECT pg_advisory_lock(hashtext('stitch_db_init'), 0)"))


def release_lock(conn) -> None:
    """Release advisory lock on the given open connection."""
    try:
        conn.execute(text("SELECT pg_advisory_unlock(hashtext('stitch_db_init'), 0)"))
    except Exception:
        # Best-effort unlock: ignore errors when releasing the lock to avoid masking original exceptions.
        pass


def ensure_meta_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {META_SCHEMA_TABLE} (
                  id INTEGER PRIMARY KEY DEFAULT 1,
                  schema_version TEXT NOT NULL,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )


def mark_schema_version(engine, version: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO {META_SCHEMA_TABLE}(id, schema_version)
                VALUES (1, :v)
                ON CONFLICT (id)
                DO UPDATE SET schema_version=EXCLUDED.schema_version, applied_at=NOW()
                """
            ),
            {"v": version},
        )


def expected_table_names() -> set[str]:
    return set(StitchBase.metadata.tables.keys())


def classify_db_state(engine, expected: set[str]) -> tuple[str, set[str]]:
    """
    Classify DB based on presence of expected tables/views.

    Returns:
      - "empty": none of the expected objects exist
      - "ok": all expected objects exist
      - "partial_or_mismatch": some but not all expected objects exist
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names(schema="public"))
    existing_views = set(insp.get_view_names(schema="public"))
    existing = existing_tables.union(existing_views)

    present = existing.intersection(expected)
    missing = expected.difference(existing)

    if not present and missing:
        return "empty", existing
    if present and not missing:
        return "ok", existing
    return "partial_or_mismatch", existing


def fail_partial(existing_tables: set[str], expected: set[str]) -> None:
    present = sorted(existing_tables.intersection(expected))
    missing = sorted(expected.difference(existing_tables))
    raise RuntimeError(
        "DB appears partially initialized or mismatched.\n"
        "Refusing to auto-heal.\n"
        f"Present expected tables: {present}\n"
        f"Missing expected tables: {missing}\n"
        "Fix by resetting the dev DB volume, or later: run migrations."
    )


def _type_repr(col: Column) -> str:
    # compile-like string is better than repr() for stability
    return str(col.type)


def schema_fingerprint(metadata) -> str:
    tables_payload = []

    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        table_payload = {
            "name": table.name,
            "columns": [],
            "primary_key": sorted(col.name for col in table.primary_key.columns),
            "indexes": [],
            "unique_constraints": [],
            "foreign_keys": [],
        }

        for col in table.columns:
            table_payload["columns"].append(
                {
                    "name": col.name,
                    "type": _type_repr(col),
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                    "unique": bool(col.unique),
                }
            )

            for fk in sorted(col.foreign_keys, key=lambda f: str(f.target_fullname)):
                table_payload["foreign_keys"].append(
                    {
                        "column": col.name,
                        "target": fk.target_fullname,
                    }
                )

        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            table_payload["indexes"].append(
                {
                    "name": idx.name,
                    "columns": sorted(col.name for col in idx.columns),
                    "unique": idx.unique,
                }
            )

        for constraint in sorted(
            table.constraints,
            key=lambda c: getattr(c, "name", "") or c.__class__.__name__,
        ):
            if constraint.__class__.__name__ == "UniqueConstraint":
                cols = sorted(col.name for col in constraint.columns)
                table_payload["unique_constraints"].append(cols)

        table_payload["columns"].sort(key=lambda c: c["name"])
        table_payload["foreign_keys"].sort(key=lambda fk: (fk["column"], fk["target"]))
        table_payload["indexes"].sort(key=lambda i: (i["name"] or "", i["columns"]))
        table_payload["unique_constraints"].sort()

        tables_payload.append(table_payload)

    payload = {"tables": tables_payload}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    logger.debug("digest: %s", digest)
    return f"orm-sha256:{digest}"


def main() -> None:
    setup_logging()

    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    logger.info("waiting for DB...")
    wait_for_db(
        engine,
        timeout_s=settings.connect_timeout_s,
        interval_s=settings.connect_retry_interval_s,
    )

    logger.info("connecting db engine...")
    conn = engine.connect()

    try:
        logger.info("acquiring advisory lock...")
        acquire_lock(conn)

        expected = expected_table_names()
        state, existing = classify_db_state(engine, expected)

        logger.info("schema state: %s", state)

        if settings.schema_mode is SchemaMode.NEVER:
            if state == "partial_or_mismatch":
                fail_partial(existing, expected)

        elif settings.schema_mode is SchemaMode.ASSERT_ONLY:
            if state == "empty":
                raise RuntimeError(
                    f"DB is empty but STITCH_DB_SCHEMA_MODE={SchemaMode.ASSERT_ONLY.value}."
                )
            if state == "partial_or_mismatch":
                fail_partial(existing, expected)
        elif settings.schema_mode is SchemaMode.IF_EMPTY:
            if state == "partial_or_mismatch":
                fail_partial(existing, expected)

            if state == "empty":
                logger.info("creating schema from ORM metadata...")
                non_view_tables = [
                    t
                    for t in StitchBase.metadata.sorted_tables
                    if not t.info.get("is_view")
                ]
                StitchBase.metadata.create_all(engine, tables=non_view_tables)
                with engine.begin() as conn:
                    create_coalesced_view(conn)
                ensure_meta_tables(engine)
                version = schema_fingerprint(StitchBase.metadata)
                mark_schema_version(engine, version=version)
            else:
                ensure_meta_tables(engine)
        else:
            raise RuntimeError(f"Unknown STITCH_DB_SCHEMA_MODE: {settings.schema_mode}")

        logger.info("done.")

    finally:
        logger.info("releasing advisory lock...")
        try:
            release_lock(conn)
        except Exception:
            logger.exception("ERROR releasing advisory lock")
        finally:
            conn.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("ERROR during db-init")
        raise
