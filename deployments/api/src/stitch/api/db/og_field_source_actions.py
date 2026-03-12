from collections.abc import Sequence

from sqlalchemy import select

from stitch.api.db.config import AsyncSession
from stitch.api.db.errors import (
    ResourceIntegrityError,
    ResourceNotFoundError,
    SourceIntegrityError,
    SourceNotFoundError,
)
from stitch.api.db.utils import partition_by_id_none
from stitch.api.entities import User
from stitch.ogsi.model import OGFieldSource, OGFieldResource

from .model import (
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
    MembershipModel,
)
from .utils import resource_model_to_entity


async def create_source(
    session: AsyncSession,
    user: User,
    source: OGFieldSource,
) -> OGFieldSource:
    """Validate raw JSON into domain model, persist canonical + original."""

    # domain validation (pydantic)
    model = OilGasFieldSourceModel.create_from_entity(source, created_by=user)

    session.add(model)
    await session.flush()
    return model.as_entity()


async def get_or_create_sources(
    session: AsyncSession,
    user: User,
    data: Sequence[OGFieldSource],
) -> Sequence[OGFieldSource]:

    return [
        src.as_entity()
        for src in await _get_or_create_source_models(session, user, data)
    ]


async def _get_or_create_source_models(
    session: AsyncSession,
    user: User,
    data: Sequence[OGFieldSource],
) -> Sequence[OilGasFieldSourceModel]:
    new_, ex_ = partition_by_id_none(data)
    src_models: list[OilGasFieldSourceModel] = [
        *(await _create_source_models(session, user, new_)),
        *(await _get_source_models(session, ex_)),
    ]
    await session.flush()

    return src_models


async def _create_source_models(
    session: AsyncSession, user: User, sources: Sequence[OGFieldSource]
) -> Sequence[OilGasFieldSourceModel]:
    if any((src.id is not None for src in sources)):
        existing = [src for src in sources if src.id is not None]
        raise SourceIntegrityError(
            f"Cannot create sources with non-None ids: {existing}"
        )
    models = [OilGasFieldSourceModel.create_from_entity(src, user) for src in sources]
    session.add_all(models)
    await session.flush()
    return models


async def _get_source_models(
    session: AsyncSession, sources: Sequence[OGFieldSource | int]
) -> Sequence[OilGasFieldSourceModel]:
    ids = [
        id_
        for id_ in [s if isinstance(s, int) else s.id for s in sources]
        if id_ is not None
    ]
    stmt = select(OilGasFieldSourceModel).where(OilGasFieldSourceModel.id.in_(ids))
    return (await session.scalars(stmt)).all()


async def attach_sources_to_resource(
    session: AsyncSession,
    resource_id: int,
    source_rows: Sequence[OGFieldSource],
    user: User,
) -> OGFieldResource:
    """Link an OG field source to a resource via membership."""
    resource = await session.get(ResourceModel, resource_id)
    if resource is None:
        raise ResourceNotFoundError(f"No resource found for id: {resource_id}")
    if len(source_rows) < 1:
        raise ResourceIntegrityError(
            f"Must pass at least 1 source row to attach to resource (id: `{resource_id}`)."
        )

    src_models = await _get_or_create_source_models(session, user, source_rows)

    # flush the session, new ids are added
    await session.flush()

    memberships = [
        MembershipModel.create(
            created_by=user,
            resource=resource,
            source=src.source,
            source_pk=src.id,
        )
        for src in src_models
    ]
    session.add_all(memberships)
    await session.flush()
    return await resource_model_to_entity(session, resource)


async def get_source(session: AsyncSession, id: int) -> OGFieldSource:
    model = await session.get(OilGasFieldSourceModel, id)
    if model is None:
        raise SourceNotFoundError(f"No OG Field Source found for id `{id}`")
    return model.as_entity()


async def get_sources(
    session: AsyncSession, ids: Sequence[int]
) -> Sequence[OGFieldSource]:
    stmt = select(OilGasFieldSourceModel).where(OilGasFieldSourceModel.id.in_(ids))
    models = (await session.scalars(stmt)).all()
    # TODO: raise if missing ids, optional
    return [model.as_entity() for model in models]


async def list_og_sources(session: AsyncSession) -> Sequence[OGFieldSource]:
    stmt = (
        select(OilGasFieldSourceModel)
        .join(MembershipModel, MembershipModel.source_pk == OilGasFieldSourceModel.id)
        .where(MembershipModel.status == MembershipStatus.ACTIVE)
        .distinct()
    )
    models = (await session.scalars(stmt)).all()
    return tuple(m.as_entity() for m in models)
