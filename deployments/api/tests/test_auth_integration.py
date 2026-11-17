"""Integration tests for JIT user provisioning in require_user."""

import pytest
from sqlalchemy import select

from stitch.api._auth import TokenClaims, require_user
from stitch.api.db.model.user import User as UserModel

OLD = ("Old Name", "old@example.com")
NEW = ("New Name", "new@example.com")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("existing", "claim_name", "claim_email", "expected"),
    [
        pytest.param(None, *NEW, NEW, id="create"),
        pytest.param(None, None, None, (None, None), id="create-without-claims"),
        pytest.param(None, "", "  ", (None, None), id="create-blank-claims-as-null"),
        pytest.param(OLD, *NEW, NEW, id="update-existing"),
        pytest.param(OLD, "   ", "", OLD, id="blank-claims-keep-existing"),
    ],
)
async def test_require_user_provisions_user_row(
    integration_session_factory, existing, claim_name, claim_email, expected
):
    sub = "auth0|user-1"
    if existing:
        async with integration_session_factory() as session:
            session.add(UserModel(sub=sub, name=existing[0], email=existing[1]))
            await session.commit()

    claims = TokenClaims(sub=sub, name=claim_name, email=claim_email)
    user = await require_user()(claims, integration_session_factory)

    async with integration_session_factory() as session:
        rows = (await session.execute(select(UserModel))).scalars().all()
    assert [(r.id, r.sub, r.name, r.email) for r in rows] == [(user.id, sub, *expected)]
    assert (user.name, user.email, user.claims) == (*expected, claims)
