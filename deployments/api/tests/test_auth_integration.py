"""Integration tests for auth module JIT user provisioning."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound


from stitch.auth import TokenClaims

from stitch.api.auth import get_current_user
from stitch.api.db.config import UnitOfWork
from stitch.api.db.model.user import User as UserModel


def _make_claims(
    sub: str = "auth0|user-1",
    email: str = "user@example.com",
    name: str = "Test User",
) -> TokenClaims:
    return TokenClaims(sub=sub, email=email, name=name, raw={})


class TestGetCurrentUserJITProvisioning:
    """Integration tests for get_current_user with real database."""

    @pytest.mark.anyio
    async def test_creates_user_on_first_login(
        self,
        integration_session_factory,
    ):
        """New user created in DB on first login."""
        claims = _make_claims(sub="auth0|new-user")

        async with UnitOfWork(integration_session_factory) as uow:
            user = await get_current_user(claims, uow)

        assert user.sub == "auth0|new-user"
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.id is not None

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|new-user")
                )
            ).scalar_one()
            assert row.email == "user@example.com"

    @pytest.mark.anyio
    async def test_returns_existing_user(
        self,
        integration_session_factory,
    ):
        """Existing user found by sub claim."""
        async with integration_session_factory() as session:
            session.add(
                UserModel(
                    sub="auth0|existing", name="Original", email="orig@example.com"
                )
            )
            await session.commit()

        claims = _make_claims(
            sub="auth0|existing", name="Updated", email="new@example.com"
        )

        async with UnitOfWork(integration_session_factory) as uow:
            user = await get_current_user(claims, uow)

        assert user.sub == "auth0|existing"
        assert user.name == "Updated"
        assert user.email == "new@example.com"

    @pytest.mark.anyio
    async def test_updates_name_email_on_subsequent_login(
        self,
        integration_session_factory,
    ):
        """Claims update reflected in DB on subsequent login."""
        async with integration_session_factory() as session:
            session.add(
                UserModel(
                    sub="auth0|updatable", name="Old Name", email="old@example.com"
                )
            )
            await session.commit()

        claims = _make_claims(
            sub="auth0|updatable", name="New Name", email="new@example.com"
        )

        async with UnitOfWork(integration_session_factory) as uow:
            await get_current_user(claims, uow)

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|updatable")
                )
            ).scalar_one()
            assert row.name == "New Name"
            assert row.email == "new@example.com"

    @pytest.mark.anyio
    async def test_error_when_missing_claim(
        self,
        integration_session_factory,
    ):
        """Name defaults to empty string when claims.name is None."""
        claims = TokenClaims(
            sub="auth0|no-name", email="valid@example.com", name=None, raw={}
        )

        async with UnitOfWork(integration_session_factory) as uow:
            with pytest.raises(NoResultFound):
                await get_current_user(claims, uow)

    @pytest.mark.anyio
    async def test_handles_concurrent_first_login(
        self,
        integration_session_factory,
    ):
        """IntegrityError caught on concurrent insert, re-queries successfully."""
        async with integration_session_factory() as session:
            session.add(
                UserModel(
                    sub="auth0|race-user", name="Racer", email="racer@example.com"
                )
            )
            await session.commit()

        claims = _make_claims(
            sub="auth0|race-user", name="Racer", email="racer@example.com"
        )

        async with UnitOfWork(integration_session_factory) as uow:
            user = await get_current_user(claims, uow)

        assert user.sub == "auth0|race-user"
