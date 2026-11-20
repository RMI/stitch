from collections.abc import Collection

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.auth import StaticAuthProvider, TokenClaims, get_auth_provider
from stitch.api.db.config import get_session_factory
from stitch.api.main import app


def override_auth(
    permissions: Collection[str],
    session_factory: async_sessionmaker[AsyncSession],
    sub: str = "test|user-1",
) -> None:
    provider = StaticAuthProvider(
        TokenClaims(
            sub=sub,
            email="test@test.com",
            name="Test User",
            permissions=frozenset(permissions),
        )
    )
    app.dependency_overrides[get_auth_provider] = lambda: provider
    app.dependency_overrides[get_session_factory] = lambda: session_factory
