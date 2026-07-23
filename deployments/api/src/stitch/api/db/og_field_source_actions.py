from collections.abc import Collection, Sequence

from sqlalchemy import func, select

from stitch.api.db.config import AsyncSession
from stitch.api.db.errors import (
    ResourceIntegrityError,
    ResourceNotFoundError,
    SourceIntegrityError,
    SourceNotFoundError,
)
from stitch.api.db.utils import partition_by_id_none
from stitch.api.entities import OGFieldQueryParams, User
from stitch.ogsi.model import OGFieldSource, OGFieldResource
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    OilGasFieldSourceModel,
    ResourceModel,
    MembershipModel,
)
from .queries import (
    base_source_query,
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


async def _get_attachable_resource(
    session: AsyncSession, resource_id: int
) -> ResourceModel:
    """Fetch a resource that is a valid attachment target.

    Raises:
        ResourceNotFoundError: if no resource exists for ``resource_id``.
        ResourceIntegrityError: if the resource has been merged (repointed);
            memberships on it would never surface in coalescing/queries.
    """
    resource = await session.get(ResourceModel, resource_id)
    if resource is None:
        raise ResourceNotFoundError(f"No resource found for id: {resource_id}")
    if resource.repointed_id is not None:
        raise ResourceIntegrityError(
            f"Cannot attach sources to a resource that has been merged "
            f"(id: `{resource_id}`, repointed to: `{resource.repointed_id}`)."
        )
    return resource


async def create_and_attach_source(
    session: AsyncSession,
    user: User,
    source: OGFieldSource,
    resource_id: int,
) -> OGFieldSource:
    """Create a new source and attach it to an existing resource.

    A source is always created (never resolved by id here), then linked to
    ``resource_id`` via an ACTIVE membership, both within the caller's unit of
    work. The resource is validated first, so an invalid target fails before any
    source is written.

    Args:
        session: db session (transaction context)
        user: the logged in User (recorded as creator)
        source: raw source data; must not carry an ``id``
        resource_id: the resource to attach the new source to

    Returns:
        The created OGFieldSource with its assigned id.

    Raises:
        SourceIntegrityError: if ``source`` carries a non-None id.
        ResourceNotFoundError: if ``resource_id`` does not exist.
        ResourceIntegrityError: if the resource has been merged (repointed).
    """
    if source.id is not None:
        raise SourceIntegrityError(
            f"Cannot create a source with a client-supplied id: {source.id}"
        )
    # Fail fast: validate the target before creating the source, so an invalid
    # resource_id never leaves a source insert to roll back.
    resource = await _get_attachable_resource(session, resource_id)

    [model] = await _create_source_models(session, user, [source])
    await _attach_source_models(session, resource, [model], user)
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


async def _attach_source_models(
    session: AsyncSession,
    resource: ResourceModel,
    src_models: Sequence[OilGasFieldSourceModel],
    user: User,
) -> None:
    """Create ACTIVE memberships linking each source model to ``resource``."""
    memberships = [
        MembershipModel.create(
            created_by=user,
            resource_id=resource.id,
            source=src.source,
            source_pk=src.id,
        )
        for src in src_models
    ]
    session.add_all(memberships)
    await session.flush()


async def attach_sources_to_resource(
    session: AsyncSession,
    resource_id: int,
    source_rows: Sequence[OGFieldSource],
    user: User,
) -> OGFieldResource:
    """Link an OG field source to a resource via membership."""
    resource = await _get_attachable_resource(session, resource_id)
    if len(source_rows) < 1:
        raise ResourceIntegrityError(
            f"Must pass at least 1 source row to attach to resource (id: `{resource_id}`)."
        )

    src_models = await _get_or_create_source_models(session, user, source_rows)
    await _attach_source_models(session, resource, src_models, user)
    return await resource_model_to_entity(session, resource)


async def get_source(
    session: AsyncSession,
    id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldSource:
    model = await session.get(OilGasFieldSourceModel, id)
    if model is None:
        raise SourceNotFoundError(f"No OG Field Source found for id `{id}`")
    if licensed_sources is not None and model.source not in licensed_sources:
        # Hide existence of unlicensed source rows.
        raise SourceNotFoundError(f"No OG Field Source found for id `{id}`")
    return model.as_entity()


async def get_source_detail(
    session: AsyncSession,
    id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldSource:
    return await get_source(session=session, id=id, licensed_sources=licensed_sources)


async def get_sources(
    session: AsyncSession, ids: Sequence[int]
) -> Sequence[OGFieldSource]:
    stmt = select(OilGasFieldSourceModel).where(OilGasFieldSourceModel.id.in_(ids))
    models = (await session.scalars(stmt)).all()
    return [model.as_entity() for model in models]


async def query(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[Sequence[OGFieldSource], int]:
    """Filtered/sorted/paginated source records (id-ordered) plus total count."""
    stmt = base_source_query(params, licensed_sources)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.scalar(count_stmt)) or 0
    stmt = stmt.limit(params.limit).offset(params.offset)
    ids = list((await session.scalars(stmt)).all())

    if not ids:
        return (), total

    headers = (
        await session.scalars(
            select(OilGasFieldSourceModel).where(OilGasFieldSourceModel.id.in_(ids))
        )
    ).all()
    by_id = {h.id: h for h in headers}
    return tuple(by_id[i].as_entity() for i in ids if i in by_id), total
