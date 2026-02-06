"""Pytest fixtures for stitch-api tests."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stitch.api.db.config import UnitOfWork, get_uow
from stitch.api.db.model import (
    GemSourceModel,
    RMIManualSourceModel,
    StitchBase,
    UserModel,
    WMSourceModel,
)
from stitch.api.deps import get_current_user
from stitch.api.entities import User
from stitch.api.main import app

from .utils import (
    GEM_DEFAULTS,
    RMI_DEFAULTS,
    WM_DEFAULTS,
)


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend only (aiosqlite doesn't support trio)."""
    return "asyncio"


@pytest.fixture
def test_user() -> User:
    """Test user entity for dependency injection."""
    return User(id=1, email="test@test.com", name="Test User", role="admin")


@pytest.fixture
def test_user_model() -> UserModel:
    """Test user ORM model for database seeding."""
    return UserModel(
        id=1,
        first_name="Test",
        last_name="User",
        email="test@test.com",
    )


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock AsyncSession with common methods."""
    session = MagicMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: MagicMock) -> MagicMock:
    """Mock async_sessionmaker that returns mock_session."""
    factory = MagicMock(spec=async_sessionmaker)
    factory.return_value = mock_session
    return factory


@pytest.fixture
def mock_uow(mock_session: MagicMock) -> MagicMock:
    """Mock UnitOfWork for unit tests."""
    uow = MagicMock(spec=UnitOfWork)
    uow.session = mock_session
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    return uow


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Reset FastAPI dependency overrides after each test."""
    yield
    app.dependency_overrides = {}


@pytest.fixture
async def async_client(test_user: User) -> AsyncIterator[AsyncClient]:
    """AsyncClient for testing FastAPI routes with mocked user."""

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


@pytest.fixture
async def integration_engine():
    """In-memory SQLite async engine for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(StitchBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def integration_session_factory(
    integration_engine,
) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to integration test engine."""
    return async_sessionmaker(
        integration_engine,
        expire_on_commit=False,
    )


@pytest.fixture
async def integration_session(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Fresh async session for integration tests."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def seeded_integration_session(
    integration_session: AsyncSession,
    test_user_model: UserModel,
) -> AsyncSession:
    """Integration session with test user already created."""
    integration_session.add(test_user_model)
    await integration_session.commit()
    return integration_session


@pytest.fixture
async def integration_client(
    integration_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_user_model: UserModel,
) -> AsyncIterator[AsyncClient]:
    """AsyncClient with real SQLite database for integration tests."""

    async with integration_session_factory() as session:
        session.add(test_user_model)
        await session.commit()

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_uow] = override_get_uow
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


@pytest.fixture
async def existing_gem_source(
    seeded_integration_session: AsyncSession,
) -> GemSourceModel:
    """Pre-create a GEM source in DB, return model with ID."""
    model = GemSourceModel(
        name=GEM_DEFAULTS["name"],
        latitude=GEM_DEFAULTS["latitude"],
        longitude=GEM_DEFAULTS["longitude"],
        country=GEM_DEFAULTS["country"],
    )
    seeded_integration_session.add(model)
    await seeded_integration_session.flush()
    return model


@pytest.fixture
async def existing_wm_source(
    seeded_integration_session: AsyncSession,
) -> WMSourceModel:
    """Pre-create a WM source in DB, return model with ID."""
    model = WMSourceModel(
        name=WM_DEFAULTS["name"],
        country=WM_DEFAULTS["country"],
    )
    seeded_integration_session.add(model)
    await seeded_integration_session.flush()
    return model


@pytest.fixture
async def existing_rmi_source(
    seeded_integration_session: AsyncSession,
) -> RMIManualSourceModel:
    """Pre-create an RMI source in DB, return model with ID."""
    model = RMIManualSourceModel(
        name=RMI_DEFAULTS["name"],
        country=RMI_DEFAULTS["country"],
        latitude=RMI_DEFAULTS["latitude"],
        longitude=RMI_DEFAULTS["longitude"],
    )
    seeded_integration_session.add(model)
    await seeded_integration_session.flush()
    return model


@pytest.fixture
async def existing_sources(
    seeded_integration_session: AsyncSession,
) -> dict[str, list[int]]:
    """Create 2 of each source type, return dict mapping source key to list of IDs."""
    session = seeded_integration_session

    gems = [
        GemSourceModel(
            name=f"GEM {i}", latitude=45.0 + i, longitude=-120.0 + i, country="USA"
        )
        for i in range(2)
    ]
    wms = [WMSourceModel(name=f"WM Field {i}", country="USA") for i in range(2)]
    rmis = [
        RMIManualSourceModel(
            name=f"RMI {i}",
            country="USA",
            latitude=40.0 + i,
            longitude=-100.0 + i,
        )
        for i in range(2)
    ]

    session.add_all(gems + wms + rmis)
    await session.flush()

    return {
        "gem": [g.id for g in gems],
        "wm": [w.id for w in wms],
        "rmi": [r.id for r in rmis],
    }
