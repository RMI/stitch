"""Pytest fixtures for stitch-api tests."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stitch.api.db.config import UnitOfWork, get_uow
from stitch.api.db.model import (
    StitchBase,
    UserModel,
)
from stitch.api.auth import get_current_user
from stitch.api.entities import User
from stitch.api.main import app


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend only (aiosqlite doesn't support trio)."""
    return "asyncio"


@pytest.fixture
def test_user() -> User:
    """Test user entity for dependency injection."""
    return User(
        id=1, sub="test|user-1", email="test@test.com", name="Test User", role="admin"
    )


@pytest.fixture
def test_user_model() -> UserModel:
    """Test user ORM model for database seeding."""
    return UserModel(
        id=1,
        sub="test|user-1",
        name="Test User",
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
    """Reset FastAPI dependency overrides and auth caches after each test."""
    yield
    app.dependency_overrides = {}
    from stitch.api.auth import get_oidc_settings, get_jwt_validator
    from stitch.api.settings import get_settings

    get_oidc_settings.cache_clear()
    get_jwt_validator.cache_clear()
    get_settings.cache_clear()


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
