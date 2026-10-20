"""Fixtures shared by the read-model tests."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stitch.api.db.model import OGFieldSourcePriority, StitchBase, UserModel
from stitch.api.db.read_model.state import rebuild_all_resource_state
from stitch.api.entities import User
from stitch.ogsi.model import SOURCE_PRIORITY

from .dataset import Dataset, seed_dataset
from .postgres import POSTGRES_URL


@pytest.fixture
async def dataset(seeded_integration_session: AsyncSession, test_user: User) -> Dataset:
    """The seeded dataset, with an empty (never rebuilt) read model."""
    return await seed_dataset(seeded_integration_session, test_user)


@pytest.fixture
async def rebuilt(
    dataset: Dataset,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> Dataset:
    """The seeded dataset after a successful full rebuild."""
    await rebuild_all_resource_state(integration_session_factory)
    return dataset


@pytest.fixture
async def pg_session_factory(
    test_user_model: UserModel,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions on the opt-in Postgres, in a schema of their own (see ``postgres.py``).

    Only for tests marked ``requires_postgres``.
    """
    assert POSTGRES_URL is not None, "mark the test with requires_postgres"
    schema = f"stit766_test_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(POSTGRES_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        POSTGRES_URL, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(StitchBase.metadata.create_all)
            await conn.execute(
                insert(OGFieldSourcePriority),
                [
                    {"source": source, "priority": i + 1}
                    for i, source in enumerate(SOURCE_PRIORITY)
                ],
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory.begin() as session:
            session.add(test_user_model)
        yield factory
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
