"""Behaviour tests for ``link_actions.match``; the cases live in ``link_actions_cases``."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import link_actions
from stitch.api.db.model import (
    MembershipModel,
    MergeCandidateItemModel,
    MergeCandidateModel,
    OilGasFieldSourceModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from tests.db.link_actions_cases import (
    ALL_CASES,
    MEMBERSHIP_AND_RESOURCE_ELIGIBILITY,
    Groups,
    State,
    case,
    params,
)

SEEDED_USER_ID = 1


async def build(session: AsyncSession, state: State) -> None:
    """Write ``state`` to the database, flushed but not committed."""
    mentioned = [rec.rid for rec in state.records]
    mentioned += list(state.repointed) + list(state.repointed.values())
    resource_count = max(mentioned, default=0)

    resources = [
        ResourceModel(created_by_id=SEEDED_USER_ID, last_updated_by_id=SEEDED_USER_ID)
        for _ in range(resource_count)
    ]
    session.add_all(resources)
    await session.flush()
    ids = [resource.id for resource in resources]
    assert ids == list(range(1, resource_count + 1)), (
        f"expected a clean database numbering resources 1..{resource_count}, "
        f"got {ids}. Something leaked from another test."
    )

    for rid, target in state.repointed.items():
        resources[rid - 1].repointed_id = target
    await session.flush()

    for rec in state.records:
        header = OilGasFieldSourceModel(
            source=rec.source,
            source_record={},
            created_by_id=SEEDED_USER_ID,
            last_updated_by_id=SEEDED_USER_ID,
        )
        session.add(header)
        await session.flush()
        for colname, value in (("name", rec.name), ("country", rec.country)):
            if value is not None:
                session.add(
                    OilGasFieldSourceValueModel(
                        source_pk=header.id, colname=colname, value_text=value
                    )
                )
        session.add(
            MembershipModel(
                resource_id=rec.rid,
                source=rec.source,
                source_pk=header.id,
                status=rec.status,
                created_by_id=SEEDED_USER_ID,
                last_updated_by_id=SEEDED_USER_ID,
            )
        )

    for index, (status, resource_ids) in enumerate(state.candidates):
        candidate = MergeCandidateModel(
            fingerprint=f"fixture-{index}",
            status=status,
            created_by_id=SEEDED_USER_ID,
            last_updated_by_id=SEEDED_USER_ID,
        )
        session.add(candidate)
        await session.flush()
        session.add_all(
            [
                MergeCandidateItemModel(
                    merge_candidate_id=candidate.id, resource_id=rid, position=position
                )
                for position, rid in enumerate(resource_ids)
            ]
        )

    await session.flush()


def assert_match_result(groups: Groups, expected: Groups) -> None:
    """Check the universal return-shape contract, then the expected value."""
    seen = [rid for group in groups for rid in group]
    assert all(len(group) >= 2 for group in groups), groups
    assert all(list(group) == sorted(group) for group in groups), groups
    assert [group[0] for group in groups] == sorted(group[0] for group in groups), (
        groups
    )
    assert len(seen) == len(set(seen)), groups
    assert groups == expected


@pytest.mark.anyio
@pytest.mark.parametrize(("state", "expected"), params(ALL_CASES))
async def test_match(
    seeded_integration_session: AsyncSession, state: State, expected: Groups
) -> None:
    """Each case's database goes in; the duplicate groups it must produce come out."""
    await build(seeded_integration_session, state)
    groups = await link_actions.match(seeded_integration_session, state.licensed)
    assert_match_result(groups, expected)


@pytest.mark.anyio
async def test_match_does_not_commit(
    seeded_integration_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``match`` reads only; the caller owns the transaction."""
    session = seeded_integration_session
    state, expected = case(
        MEMBERSHIP_AND_RESOURCE_ELIGIBILITY, "both-memberships-active", as_param=False
    )
    await build(session, state)

    monkeypatch.setattr(
        session,
        "commit",
        AsyncMock(side_effect=AssertionError("match must not commit")),
    )
    groups = await link_actions.match(session, state.licensed)

    assert_match_result(groups, expected)
