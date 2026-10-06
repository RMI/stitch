"""Shared helpers for the duplicate-hunting scripts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import URL, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from stitch.api.db.model import UserModel
from stitch.api.entities import User

from .candidates import CANDIDATES_PATH, RESOURCES_PATH
from .paths import data_dir, repo_root, scripts_dir
from .settings import script_settings

__all__ = [
    "CANDIDATES_PATH",
    "DATA_DIR",
    "DEV_SUB",
    "REPO_ROOT",
    "RESOURCES_PATH",
    "SCRIPTS_DIR",
    "dev_user",
    "distinct_sources",
    "flatten_list_item",
    "open_session",
]

SCRIPTS_DIR = scripts_dir()
REPO_ROOT = repo_root()
DATA_DIR = data_dir()

DEV_SUB = "dev|local-placeholder"


@asynccontextmanager
async def open_session(db_url: URL | None = None) -> AsyncIterator[AsyncSession]:
    """Session on the configured Postgres: local docker by default."""
    url = db_url or script_settings().database_url()
    print(f"db: {url}")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


async def dev_user(session: AsyncSession) -> User:
    """The local dev user, for the audit columns on anything written."""
    model = await session.scalar(select(UserModel).where(UserModel.sub == DEV_SUB))
    if model is None:
        model = UserModel(sub=DEV_SUB, email="dev@example.com", name="Dev User")
        session.add(model)
        await session.commit()
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
