"""Pytest fixtures for stitch-api tests."""

from collections.abc import AsyncIterator
from functools import partial
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from polyfactory.pytest_plugin import register_fixture
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stitch.auth import TokenClaims
from stitch.auth.permissions import ALL_PERMISSIONS

from stitch.api.db.config import UnitOfWork, get_uow
from stitch.api.db.model import (
    StitchBase,
    UserModel,
)
from stitch.api.auth import get_current_user, get_token_claims
from stitch.api.entities import User
from stitch.api.main import app
from stitch.api.settings import PostgresConfig, Settings, SqliteConfig, get_settings
from .factories import OGFieldBaseFactory, ResourceFactory
from .utils import make_create_resource, make_resource, make_source


# The settings classes read a ``.env`` file relative to the working directory,
# and ``make`` runs the suite from the repo root, so ``Settings()`` would
# otherwise pick up a developer's local ``.env`` and mask the declared code
# defaults that tests assert against. Disable dotenv loading here; real env vars
# (e.g. OTEL_TRACES_EXPORTER, set in the rootdir conftest) still win. Importing
# ``app`` above already built the cached settings singleton off ``.env``, so
# clear it — the next read rebuilds it from defaults.
for _settings_cls in (PostgresConfig, Settings, SqliteConfig):
    _settings_cls.model_config["env_file"] = None
get_settings.cache_clear()


_ALL_LICENSED_CLAIMS = TokenClaims(
    sub="test|user-1",
    email="test@test.com",
    name="Test User",
    permissions=ALL_PERMISSIONS,
)


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

    def override_get_token_claims() -> TokenClaims:
        return _ALL_LICENSED_CLAIMS

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_token_claims] = override_get_token_claims

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


@pytest.fixture
async def integration_engine():
    """In-memory SQLite async engine for integration tests."""
    non_view_tables = [
        t for t in StitchBase.metadata.sorted_tables if not t.info.get("is_view")
    ]
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(StitchBase.metadata.create_all, tables=non_view_tables)
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

    def override_get_token_claims() -> TokenClaims:
        return _ALL_LICENSED_CLAIMS

    app.dependency_overrides[get_uow] = override_get_uow
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_token_claims] = override_get_token_claims

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


register_fixture(ResourceFactory, name="og_field_resource_factory", scope="function")
register_fixture(OGFieldBaseFactory, name="og_field_base_factory", scope="function")


@pytest.fixture(scope="function")
def source_maker(og_field_base_factory: OGFieldBaseFactory):
    return partial(make_source, fact=og_field_base_factory)


@pytest.fixture(scope="function")
def og_res_fact(
    og_field_resource_factory: ResourceFactory,
    og_field_base_factory: OGFieldBaseFactory,
):
    fact = partial(
        make_resource, fact=og_field_resource_factory, base_fact=og_field_base_factory
    )
    return fact


@pytest.fixture(scope="function")
def og_create_res_fact(
    og_field_resource_factory: ResourceFactory,
    og_field_base_factory: OGFieldBaseFactory,
):
    fact = partial(
        make_create_resource,
        factory=og_field_resource_factory,
        base_factory=og_field_base_factory,
    )
    return fact
