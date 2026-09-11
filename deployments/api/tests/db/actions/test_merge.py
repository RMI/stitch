import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.errors import ResourceIntegrityError
from stitch.api.db.model import ResourceModel
from stitch.api.entities import User


class TestMergeResourcesUnit:
    """Direct coverage for apply_resource_merge's guards."""

    @pytest.mark.anyio
    async def test_apply_resource_merge_rejects_already_repointed_input(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """An already-merged input is rejected with an actionable, id-naming message.

        Regression guard for STIT-418: the error must name the terminal resource,
        not leak a ``repr()`` memory address.
        """
        session = seeded_integration_session
        root = ResourceModel.create(created_by=test_user)
        session.add(root)
        await session.flush()

        moved = ResourceModel.create(created_by=test_user, repointed_to=root.id)
        other = ResourceModel.create(created_by=test_user)
        session.add_all([moved, other])
        await session.flush()

        with pytest.raises(ResourceIntegrityError) as exc_info:
            await resource_actions.apply_resource_merge(
                session=session,
                user=test_user,
                resource_ids=[moved.id, other.id],
            )

        message = str(exc_info.value)
        assert f"resource {moved.id} is now resource {root.id}" in message
        assert "object at 0x" not in message
