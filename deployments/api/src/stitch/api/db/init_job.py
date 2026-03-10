from __future__ import annotations

import os
import sys
import time
from enum import Enum
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from stitch.api.db.model import (
    CCReservoirsSourceModel,
    GemSourceModel,
    MembershipModel,
    RMIManualSourceModel,
    ResourceModel,
    StitchBase,
    UserModel,
    WMSourceModel,
)
from stitch.api.entities import (
    GemData,
    RMIManualData,
    User as UserEntity,
    WMData,
)

"""
DB init/seed job.

This module is intended to be run as a one-shot job (e.g. a `db-init` service)
*before* the API starts. It can:
  - create schema from SQLAlchemy metadata if the DB is empty
  - fail fast on partial/mismatched schemas (no auto-healing)
  - apply a seed profile once and record that it ran

Role separation / env vars:
  - The recommended setup uses two Postgres roles:
      * migrator/seeder role: DDL + seed (used by the init job)
      * app role: no DDL (used by the API)
  - Set STITCH_DB_USER / STITCH_DB_PASSWORD on a per-service basis to choose
    which role connects (migrator for `db-init`, app for `api`).
  - POSTGRES_* variables are supported as a fallback for local convenience and
    backwards compatibility.
"""

META_SCHEMA_TABLE = "stitch_schema_meta"
META_SEED_TABLE = "stitch_seed_meta"


class SchemaMode(str, Enum):
    IF_EMPTY = "if-empty"
    ASSERT_ONLY = "assert-only"
    NEVER = "never"


class SeedProfile(str, Enum):
    DEV = "dev"


class SeedMode(str, Enum):
    IF_NEEDED = "if-needed"
    NEVER = "never"


@dataclass(frozen=True)
class Settings:
    schema_mode: SchemaMode
    seed_profile: SeedProfile
    seed_mode: SeedMode
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
        seed_profile=SeedProfile(_env("STITCH_DB_SEED_PROFILE", SeedProfile.DEV.value)),
        seed_mode=SeedMode(_env("STITCH_DB_SEED_MODE", SeedMode.IF_NEEDED.value)),
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
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {META_SEED_TABLE} (
                  profile TEXT PRIMARY KEY,
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


def seed_already_applied(engine, profile: str) -> bool:
    with engine.connect() as conn:
        try:
            row = conn.execute(
                text(f"SELECT 1 FROM {META_SEED_TABLE} WHERE profile=:p"),
                {"p": profile},
            ).first()
            return row is not None
        except OperationalError:
            return False


def mark_seed_applied(engine, profile: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {META_SEED_TABLE}(profile) VALUES (:p) ON CONFLICT DO NOTHING"
            ),
            {"p": profile},
        )


def expected_table_names() -> set[str]:
    return set(StitchBase.metadata.tables.keys())


def classify_db_state(engine, expected: set[str]) -> tuple[str, set[str]]:
    """
    Classify DB based only on presence of expected tables.

    Returns:
      - "empty": none of the expected tables exist
      - "ok": all expected tables exist (columns/constraints not checked)
      - "partial_or_mismatch": some but not all expected tables exist
    """
    insp = inspect(engine)
    existing = set(insp.get_table_names(schema="public"))

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


# -------------------------
# Seed dataset(s)
# -------------------------


def create_seed_user() -> UserModel:
    return UserModel(
        id=1,
        sub="seed|system",
        name="Seed User",
        email="seed@example.com",
    )


def create_dev_user() -> UserModel:
    return UserModel(
        id=2,
        sub="dev|local-placeholder",
        name="Dev Deverson",
        email="dev@example.com",
    )


def create_seed_sources():
    gem_sources = [
        GemSourceModel.from_entity(
            GemData(name="Permian Basin Field", country="USA", lat=31.8, lon=-102.3)
        ),
        GemSourceModel.from_entity(
            GemData(name="North Sea Platform", country="GBR", lat=57.5, lon=1.5)
        ),
        GemSourceModel.from_entity(
            GemData(name="Merge Target Field", country="YYZ", lat=13.37, lon=13.37)
        ),
    ]
    for i, src in enumerate(gem_sources, start=1):
        src.id = i

    wm_sources = [
        WMSourceModel.from_entity(
            WMData(
                field_name="Eagle Ford Shale", field_country="USA", production=125000.5
            )
        ),
        WMSourceModel.from_entity(
            WMData(field_name="Ghawar Field", field_country="SAU", production=500000.0)
        ),
        WMSourceModel.from_entity(
            WMData(
                field_name="Merge Consumed Field",
                field_country="YYZ",
                production=1337.0,
            )
        ),
    ]
    for i, src in enumerate(wm_sources, start=1):
        src.id = i

    rmi_sources = [
        RMIManualSourceModel.from_entity(
            RMIManualData(
                name_override="Custom Override Name",
                gwp=25.5,
                gor=0.45,
                country="CAN",
                latitude=56.7,
                longitude=-111.4,
            )
        ),
    ]
    for i, src in enumerate(rmi_sources, start=1):
        src.id = i

    # CC Reservoir sources are intentionally omitted from the dev seed profile;
    # the CCReservoirsSourceModel table is still created from SQLAlchemy metadata.
    cc_sources: list[CCReservoirsSourceModel] = []

    return gem_sources, wm_sources, rmi_sources, cc_sources


def create_seed_resources(user: UserEntity) -> list[ResourceModel]:
    resources = [
        ResourceModel.create(user, name="Multi-Source Asset", country="USA"),
        ResourceModel.create(user, name="Single Source Asset", country="GBR"),
        ResourceModel.create(user, name="Merge Target", country="YYZ"),
        ResourceModel.create(user, name="Merge Consumed", country="YYZ"),
    ]
    for i, res in enumerate(resources, start=1):
        res.id = i
    return resources


def create_seed_memberships(
    user: UserEntity,
    resources: list[ResourceModel],
    gem_sources: list[GemSourceModel],
    wm_sources: list[WMSourceModel],
    rmi_sources: list[RMIManualSourceModel],
) -> list[MembershipModel]:
    memberships = [
        MembershipModel.create(user, resources[0], "gem", gem_sources[0].id),
        MembershipModel.create(user, resources[0], "wm", wm_sources[0].id),
        MembershipModel.create(user, resources[0], "rmi", rmi_sources[0].id),
        MembershipModel.create(user, resources[1], "gem", gem_sources[1].id),
        MembershipModel.create(user, resources[2], "gem", gem_sources[2].id),
        MembershipModel.create(user, resources[3], "wm", wm_sources[2].id),
    ]
    for i, mem in enumerate(memberships, start=1):
        mem.id = i
    return memberships


def reset_sequences(engine, tables: Iterable[str]) -> None:
    with engine.begin() as conn:
        for t in tables:
            conn.execute(
                text(
                    f"SELECT setval('{t}_id_seq', "
                    f"(SELECT COALESCE(MAX(id), 0) + 1 FROM {t}), false);"
                )
            )


def seed_dev(engine) -> None:
    with Session(engine) as session:
        user_model = create_seed_user()
        session.add(user_model)
        session.flush()

        dev_model = create_dev_user()
        session.add(dev_model)
        session.flush()

        user_entity = UserEntity(
            id=user_model.id,
            sub=user_model.sub,
            email=user_model.email,
            name=user_model.name,
        )

        dev_entity = UserEntity(
            id=dev_model.id,
            sub=dev_model.sub,
            email=dev_model.email,
            name=dev_model.name,
        )

        gem_sources, wm_sources, rmi_sources, cc_sources = create_seed_sources()
        session.add_all(gem_sources + wm_sources + rmi_sources + cc_sources)

        resources = create_seed_resources(user_entity)
        resources = create_seed_resources(dev_entity)
        session.add_all(resources)

        memberships = create_seed_memberships(
            user_entity, resources, gem_sources, wm_sources, rmi_sources
        )
        session.add_all(memberships)

        session.commit()

    reset_sequences(
        engine,
        tables=[
            "users",
            "gem_sources",
            "wm_sources",
            "rmi_manual_sources",
            "resources",
            "memberships",
        ],
    )


def seed(engine, profile: SeedProfile | str) -> None:
    if profile == "dev":
        seed_dev(engine)
        return
    raise RuntimeError(f"Unknown seed profile '{profile}'")


def main() -> None:
    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    print("[db-init] waiting for DB...", flush=True)
    wait_for_db(
        engine,
        timeout_s=settings.connect_timeout_s,
        interval_s=settings.connect_retry_interval_s,
    )

    print("[db-init] connecting db engine...", flush=True)
    conn = engine.connect()
    try:
        print("[db-init] acquiring advisory lock...", flush=True)
        acquire_lock(conn)
        expected = expected_table_names()
        state, existing = classify_db_state(engine, expected)
        print(f"[db-init] schema state: {state}", flush=True)

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
                print("[db-init] creating schema from ORM metadata...", flush=True)
                StitchBase.metadata.create_all(engine)
                ensure_meta_tables(engine)
                mark_schema_version(engine, version="dev-orm-metadata")
            else:
                ensure_meta_tables(engine)
        else:
            raise RuntimeError(f"Unknown STITCH_DB_SCHEMA_MODE: {settings.schema_mode}")

        if settings.seed_mode is not SeedMode.NEVER and settings.seed_profile:
            ensure_meta_tables(engine)
            if seed_already_applied(engine, settings.seed_profile):
                print(
                    f"[db-init] seed '{settings.seed_profile}' already applied; skipping.",
                    flush=True,
                )
            else:
                print(f"[db-init] seeding '{settings.seed_profile}'...", flush=True)
                seed(engine, settings.seed_profile)
                mark_seed_applied(engine, settings.seed_profile)
                print(f"[db-init] seed '{settings.seed_profile}' applied.", flush=True)

        print("[db-init] done.", flush=True)
    finally:
        print("[db-init] releasing advisory lock...", flush=True)
        try:
            release_lock(conn)
        except Exception as e:
            print(
                f"[db-init] ERROR releasing advisory lock: {e}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            conn.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[db-init] ERROR: {e}", file=sys.stderr, flush=True)
        raise
