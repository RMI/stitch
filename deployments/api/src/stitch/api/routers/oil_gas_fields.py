from collections.abc import Sequence
from fastapi import APIRouter

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.auth import CurrentUser
from stitch.api.entities import Resource

from stitch.ogsi.model import OGFieldResource, OGFieldView

router = APIRouter(
    prefix="/oil-gas-fields",
    tags=["oil_gas_fields"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_resources(
    *, uow: UnitOfWorkDep, user: CurrentUser
) -> Sequence[Resource]:
    return await resource_actions.get_all(session=uow.session)


@router.get("/{id}", response_model=OGFieldView)
async def get_resource(*, uow: UnitOfWorkDep, user: CurrentUser, id: int) -> OGFieldView:
    res: Resource = await resource_actions.get(session=uow.session, id=id)

    og_res = OGFieldResource(
        id = res.id,
        name = res.name,
        country = res.country,
        source_data = res.source_data
    )
    return og_res.to_view()


# TODO: consider sub-routes (this would be a repeatable pattern for other "resource" objects)
#  * GET /{id}/sources - get og_field_sources for og_field_resource
#  * GET <oil-gas-fields>/sources - get/query all og_field_sources (only useful if we have other "resources")
#  * POST /{id}/sources - attach og_field_source objects to og_field_resource
#  * POST <oil-gas-fields>/sources - create new og_field_sources
#  * Are we every going to detatch a source from a resource?


@router.post("/", response_model=Resource)
async def create_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_in: Resource
) -> Resource:
    return await resource_actions.create(
        session=uow.session, user=user, resource=resource_in
    )
