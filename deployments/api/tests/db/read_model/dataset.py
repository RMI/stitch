"""A small deterministic dataset covering what can change a coalesced answer.

Default source priority is rmi > wm > ccr > bc > alb > nor > gem > llm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceSourcePriority,
    OGFieldResourceState,
    ResourceModel,
)
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.entities import User
from tests.utils import make_source_model

ALPHA_OWNERS = [{"name": "Acme", "stake": 60.0}, {"name": "Globex", "stake": None}]
BETA_OPERATORS = [{"name": "Aramco", "stake": 100.0}]


@dataclass(frozen=True)
class Dataset:
    alpha: int  # public sources only; competing names; JSON + numeric values
    beta: int  # wm outranks gem for name
    gamma: int  # ccr outranks alb for basin; ccr alone supplies region
    delta: int  # wm only: an all-null shell for profiles without wm
    epsilon: int  # per-resource overrides invert the default order
    empty: int  # active membership whose source has no values
    inactive: int  # only an inactive membership: not listable
    bare: int  # no memberships: not listable
    merged: int  # current resource created by merging zeta_a + zeta_b
    zeta_a: int  # merged away
    zeta_b: int  # merged away

    @property
    def listable(self) -> set[int]:
        return {
            self.alpha,
            self.beta,
            self.gamma,
            self.delta,
            self.epsilon,
            self.empty,
            self.merged,
        }


async def new_resource(session: AsyncSession, user: User) -> int:
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()
    return resource.id


async def attach(
    session: AsyncSession,
    user: User,
    resource_id: int,
    source: str,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    **attrs: Any,
) -> int:
    """Create a source with ``attrs`` and attach it directly (no action hooks)."""
    model = make_source_model(source=source, created_by_id=user.id, **attrs)
    session.add(model)
    await session.flush()
    session.add(
        MembershipModel.create(
            created_by=user,
            resource_id=resource_id,
            source=model.source,
            source_pk=model.id,
            status=status,
        )
    )
    await session.flush()
    return model.id


def override(
    user: User, resource_id: int, source: str, source_pk: int, field: str, rank: int
) -> OGFieldResourceSourcePriority:
    return OGFieldResourceSourcePriority.create(
        created_by=user,
        resource_id=resource_id,
        source=source,
        source_pk=source_pk,
        colname=field,
        priority=rank,
    )


async def seed_dataset(session: AsyncSession, user: User) -> Dataset:
    """Seed the dataset and commit it, with no read-model state."""
    alpha = await new_resource(session, user)
    await attach(
        session,
        user,
        alpha,
        "gem",
        name="Alpha GEM",
        country="USA",
        basin="Permian",
        latitude=31.5,
        discovery_year=1921,
        owners=ALPHA_OWNERS,
    )
    await attach(
        session,
        user,
        alpha,
        "rmi",
        name="Alpha RMI",
        region="North America",
        field_status="Producing",
    )

    beta = await new_resource(session, user)
    await attach(session, user, beta, "gem", name="Beta GEM", country="SAU")
    await attach(
        session,
        user,
        beta,
        "wm",
        name="Beta WM",
        operators=BETA_OPERATORS,
        production_start_year=1951,
    )

    gamma = await new_resource(session, user)
    await attach(session, user, gamma, "llm", name="Gamma", country="NOR")
    await attach(
        session, user, gamma, "ccr", region="North Sea", basin="Viking", fid_year=1970
    )
    await attach(
        session, user, gamma, "alb", state_province="Rogaland", basin="Alb Basin"
    )

    delta = await new_resource(session, user)
    await attach(session, user, delta, "wm", name="Delta", country="GBR")

    epsilon = await new_resource(session, user)
    bc = await attach(session, user, epsilon, "bc", name="Epsilon BC", country="CAN")
    nor = await attach(session, user, epsilon, "nor", name="Epsilon NOR")
    wm = await attach(session, user, epsilon, "wm", basin="WM Basin")
    ccr = await attach(session, user, epsilon, "ccr", basin="CCR Basin")
    session.add_all(
        [
            override(user, epsilon, "nor", nor, "name", 0),
            override(user, epsilon, "bc", bc, "name", 1),
            override(user, epsilon, "ccr", ccr, "basin", 0),
            override(user, epsilon, "wm", wm, "basin", 1),
        ]
    )

    empty = await new_resource(session, user)
    await attach(session, user, empty, "gem")

    inactive = await new_resource(session, user)
    await attach(
        session,
        user,
        inactive,
        "gem",
        name="Inactive",
        status=MembershipStatus.INACTIVE,
    )

    bare = await new_resource(session, user)

    zeta_a = await new_resource(session, user)
    await attach(session, user, zeta_a, "gem", name="Zeta", country="IND")
    zeta_b = await new_resource(session, user)
    await attach(session, user, zeta_b, "rmi", name="Zeta RMI", longitude=78.9)
    merged = await resource_actions.apply_resource_merge(
        session, user, [zeta_a, zeta_b]
    )
    assert merged.id is not None

    # The merge action maintains read-model state as it goes; start every test
    # from an empty read model instead, as after the schema migration.
    await session.execute(delete(OGFieldResourceState))
    await session.commit()
    return Dataset(
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        delta=delta,
        epsilon=epsilon,
        empty=empty,
        inactive=inactive,
        bare=bare,
        merged=merged.id,
        zeta_a=zeta_a,
        zeta_b=zeta_b,
    )


async def dump_state(session: AsyncSession) -> dict[tuple[int, int], dict[str, Any]]:
    """Every stored row as ``(resource_id, mask) -> {field..., provenance}``."""
    # Plain table rows, not ORM entities, so nothing stale comes from the
    # session's identity map.
    rows = (await session.execute(select(OGFieldResourceState.__table__))).all()
    return {
        (row.resource_id, row.permission_mask): {
            **{field: getattr(row, field) for field in ATTRIBUTE_NAMES},
            "provenance": row.provenance,
        }
        for row in rows
    }
