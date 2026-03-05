from typing import Mapping

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from sqlalchemy import select

from stitch.ogsi.model.og_field import OilGasFieldBase

from .model import OilGasFieldSourceModel, ResourceModel, MembershipModel


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

    model = OilGasFieldSourceModel(
        source_system=source_system,
        source_ref=source_ref,
        name=domain.name,
        country=domain.country,
        basin=domain.basin,
        payload=domain.model_dump(),
        original_payload=raw_payload,
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
            source="og_field",
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
        .join(MembershipModel, MembershipModel.resource_id == ResourceModel.id)
        .where(MembershipModel.source == "og_field")
        .distinct()
    )
    return (await session.scalars(stmt)).all()
