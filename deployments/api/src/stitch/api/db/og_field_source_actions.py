import asyncio

from functools import partial

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from stitch.ogsi.model.og_field import OilGasFieldBase

from .model import OilGasFieldSourceModel, ResourceModel, MembershipModel
from .resource_actions import resource_model_to_entity


async def create_source(
    session,
    raw_payload: dict[str, object],
    *,
    source_system: str | None = None,
    source_ref: str | None = None,
) -> OilGasFieldSourceModel:
    """Validate raw JSON into domain model, persist canonical + original."""

    # domain validation (pydantic)
    domain: OilGasFieldBase = OilGasFieldBase.model_validate(raw_payload)

    dumped = domain.model_dump(mode="json")

    model = OilGasFieldSourceModel(
        source=source_system,
        source_ref=source_ref,
        name=domain.name,
        country=domain.country,
        basin=domain.basin,
        latitude=domain.latitude,
        longitude=domain.longitude,
        last_updated=domain.last_updated,
        name_local=domain.name_local,
        state_province=domain.state_province,
        region=domain.region,
        owners=dumped.get("owners"),
        operators=dumped.get("operators"),
        location_type=dumped.get("location_type"),
        production_conventionality=dumped.get("production_conventionality"),
        primary_hydrocarbon_group=dumped.get("primary_hydrocarbon_group"),
        reservoir_formation=domain.reservoir_formation,
        discovery_year=domain.discovery_year,
        production_start_year=domain.production_start_year,
        fid_year=domain.fid_year,
        field_status=dumped.get("field_status"),
    )
    session.add(model)
    await session.flush()
    return model


async def attach_to_resource(
    session,
    resource_id: int,
    source_row: OilGasFieldSourceModel,
    created_by,
):
    """Link an OG field source to a resource via membership."""
    session.add(
        MembershipModel.create(
            created_by=created_by,
            resource=session.get(ResourceModel, resource_id),
            source="rmi",
            source_pk=source_row.id,
        )
    )
    await session.flush()


async def get_source(session, id: int) -> OilGasFieldSourceModel:
    model = await session.get(OilGasFieldSourceModel, id)
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No OG field source with id `{id}`"
        )
    return model

async def list_og_resources(session):
    stmt = (
        select(ResourceModel)
        .where(ResourceModel.repointed_id.is_(None))
        .join(MembershipModel, MembershipModel.resource_id == ResourceModel.id)
        .options(selectinload(ResourceModel.memberships))
        .distinct()
    )
    models = (await session.scalars(stmt)).all()
    fn = partial(resource_model_to_entity, session)
    return await asyncio.gather(*[fn(m) for m in models])
