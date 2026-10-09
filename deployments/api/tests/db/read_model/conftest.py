"""Fixtures shared by the read-model tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db.read_model.state import rebuild_all_resource_state
from stitch.api.entities import User

from .dataset import Dataset, seed_dataset


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
