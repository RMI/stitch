from collections.abc import Sequence

from fastapi import APIRouter

import stitch.api.db.resources as resource_repo
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.deps import CurrentUser
from stitch.api.entities import CreateResource, Resource


router = APIRouter(
    prefix="/resources",
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_resources() -> Sequence[Resource]: ...


@router.get("/{id}", response_model=Resource)
async def get_resource(*, uow: UnitOfWorkDep, id: int) -> Resource:
    return await resource_repo.get(session=uow.session, id=id)


@router.post("/", response_model=Resource)
async def create_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_in: CreateResource
) -> Resource:
    return await resource_repo.create(
        session=uow.session, user=user, resource=resource_in
    )


@router.post("/merge/...")
async def merge_resource(): ...
