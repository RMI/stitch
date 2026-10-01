"""Shared helpers for the duplicate-hunting scripts.

Local developer tooling, not shipped with any deployment.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from stitch.api.db.model import UserModel
from stitch.api.entities import User
from stitch.api.settings import PostgresConfig

from .paths import data_dir, repo_root, scripts_dir

# Derived from the repo root, not from __file__: this module sits one level
# below scripts/, so __file__.parent would point at scripts/lib/.
SCRIPTS_DIR = scripts_dir()
REPO_ROOT = repo_root()
DATA_DIR = data_dir()
RESOURCES_PATH = DATA_DIR / "resources.jsonl"
CANDIDATES_PATH = DATA_DIR / "candidates.json"

# Same sub as scripts/etl.py, so everything these scripts write is attributed to
# one row instead of whichever user happened to exist first.
DEV_SUB = "dev|local-placeholder"


@asynccontextmanager
async def open_session() -> AsyncIterator[AsyncSession]:
    """Session on the local docker Postgres.

    These scripts call the API's action functions directly rather than over HTTP:
    no router, no auth layer, no bearer token, and no round trip per record. The
    actions are where the logic lives; the routes are thin wrappers over them.

    `.env` sets POSTGRES_HOST=db, the compose service name, which only resolves
    inside the compose network. These run on the host, so the host is overridden
    to localhost (the db service publishes 5432). Set SPIKE_DB_HOST to change it.
    Everything else comes from `.env` via the API's own PostgresConfig.
    """
    cfg = PostgresConfig()
    url = cfg.to_url().set(host=os.environ.get("SPIKE_DB_HOST", "localhost"))
    print(f"db: {url.username}@{url.host}:{url.port}/{url.database}")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


async def dev_user(session: AsyncSession) -> User:
    """The local dev user, for the audit columns on anything written.

    The action layer only reads `user.id`, but `created_by_id` and
    `last_updated_by_id` are non-nullable foreign keys to `users.id`, so a real
    row has to exist. Create it rather than requiring the API to have run.
    """
    model = await session.scalar(select(UserModel).where(UserModel.sub == DEV_SUB))
    if model is None:
        model = UserModel(sub=DEV_SUB, email="dev@example.com", name="Dev User")
        session.add(model)
        await session.commit()
        # The commit expires the instance, and reloading an expired attribute on
        # an AsyncSession has to be awaited -- reading model.id straight after
        # would raise MissingGreenlet.
        await session.refresh(model)
    return User(id=model.id, sub=model.sub, email=model.email, name=model.name)


def distinct_sources(provenance: dict[str, Any] | None) -> list[str]:
    """The set of source keys that won at least one field on a resource."""
    if not provenance:
        return []
    return sorted({source for source in provenance.values() if source})


def flatten_list_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project a dumped OGFieldListItemView down to the fields the matcher needs."""
    data = item["data"]
    return {
        "id": item["id"],
        "name": data["name"],
        "country": data["country"],
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "name_local": data["name_local"],
        "state_province": data["state_province"],
        "region": data["region"],
        "basin": data["basin"],
        "operators": [operator["name"] for operator in data["operators"] or []],
        "owners": [owner["name"] for owner in data["owners"] or []],
        "field_status": data["field_status"],
        "sources": distinct_sources(item["provenance"]),
    }
