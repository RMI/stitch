"""Integration tests for auth module JIT user provisioning."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


from stitch.auth import TokenClaims

from stitch.api.auth import get_current_user
from stitch.api.db.config import UnitOfWork
from stitch.api.db.model.user import User as UserModel


def _make_claims(
    sub: str = "auth0|user-1",
    email: str | None = "user@example.com",
    name: str | None = "Test User",
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

        user = await get_current_user(claims, integration_session_factory)

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

        user = await get_current_user(claims, integration_session_factory)

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

        await get_current_user(claims, integration_session_factory)

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|updatable")
                )
            ).scalar_one()
            assert row.name == "New Name"
            assert row.email == "new@example.com"

    @pytest.mark.anyio
    async def test_creates_user_with_null_claims(
        self,
        integration_session_factory,
    ):
        """User can be JIT-provisioned when name and email claims are absent."""
        claims = _make_claims(sub="auth0|no-claims", email=None, name=None)

        user = await get_current_user(claims, integration_session_factory)

        assert user.sub == "auth0|no-claims"
        assert user.email is None
        assert user.name is None

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|no-claims")
                )
            ).scalar_one()
            assert row.email is None
            assert row.name is None

    @pytest.mark.anyio
    async def test_backfills_missing_fields_on_subsequent_login(
        self,
        integration_session_factory,
    ):
        """Null name/email columns get populated when later claims provide them."""
        async with integration_session_factory() as session:
            session.add(UserModel(sub="auth0|backfill", name=None, email=None))
            await session.commit()

        claims = _make_claims(
            sub="auth0|backfill", name="Filled In", email="filled@example.com"
        )

        user = await get_current_user(claims, integration_session_factory)

        assert user.name == "Filled In"
        assert user.email == "filled@example.com"

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|backfill")
                )
            ).scalar_one()
            assert row.name == "Filled In"
            assert row.email == "filled@example.com"

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

        user = await get_current_user(claims, integration_session_factory)

        assert user.sub == "auth0|race-user"

    @pytest.mark.anyio
    async def test_concurrent_first_login_backfills_missing_fields(
        self,
        integration_session_factory,
    ):
        """Concurrent winner with null fields still gets current claims back-filled."""
        async with integration_session_factory() as session:
            session.add(UserModel(sub="auth0|race-backfill", name=None, email=None))
            await session.commit()

        claims = _make_claims(
            sub="auth0|race-backfill",
            name="Filled After Race",
            email="race@example.com",
        )

        user = await get_current_user(claims, integration_session_factory)

        assert user.name == "Filled After Race"
        assert user.email == "race@example.com"

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|race-backfill")
                )
            ).scalar_one()
            assert row.name == "Filled After Race"
            assert row.email == "race@example.com"

    @pytest.mark.anyio
    async def test_provisioning_survives_caller_rollback(
        self,
        integration_session_factory,
    ):
        """JIT-provisioned user persists even if the caller's transaction rolls back."""
        claims = _make_claims(sub="auth0|durable")

        with pytest.raises(RuntimeError):
            async with UnitOfWork(integration_session_factory):
                await get_current_user(claims, integration_session_factory)
                raise RuntimeError("simulated handler failure")

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|durable")
                )
            ).scalar_one()
            assert row.sub == "auth0|durable"

    @pytest.mark.anyio
    async def test_backfill_survives_caller_rollback(
        self,
        integration_session_factory,
    ):
        """Claim back-fill persists even if the caller's transaction rolls back."""
        async with integration_session_factory() as session:
            session.add(UserModel(sub="auth0|durable-backfill", name=None, email=None))
            await session.commit()

        claims = _make_claims(
            sub="auth0|durable-backfill",
            name="Filled",
            email="filled@example.com",
        )

        with pytest.raises(RuntimeError):
            async with UnitOfWork(integration_session_factory):
                await get_current_user(claims, integration_session_factory)
                raise RuntimeError("simulated handler failure")

        async with integration_session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == "auth0|durable-backfill")
                )
            ).scalar_one()
            assert row.name == "Filled"
            assert row.email == "filled@example.com"


class TestGetCurrentUserIntegrityErrorHandling:
    """Unit tests for narrowed IntegrityError recovery."""

    @pytest.mark.anyio
    async def test_unrelated_integrity_error_propagates(self):
        """An IntegrityError without a concurrent row must propagate, not be masked."""
        miss_result = MagicMock()
        miss_result.scalar_one_or_none = MagicMock(return_value=None)

        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=miss_result)
        session.add = MagicMock()
        session.commit = AsyncMock(
            side_effect=IntegrityError(
                "INSERT INTO users", {}, Exception("simulated check constraint")
            )
        )
        session.rollback = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        factory = MagicMock(return_value=session)

        claims = _make_claims(sub="auth0|broken")

        with pytest.raises(IntegrityError):
            await get_current_user(claims, factory)

        session.rollback.assert_awaited_once()
