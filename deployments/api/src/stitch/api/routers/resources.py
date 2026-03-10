import logging

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

from stitch.api.db import resource_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.auth import CurrentUser
from stitch.api.entities import CreateResource, Resource

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/resources",
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_resources(
    *, uow: UnitOfWorkDep, user: CurrentUser
) -> Sequence[Resource]:
    return await resource_actions.get_all(session=uow.session)


@router.get("/{id}", response_model=Resource)
async def get_resource(*, uow: UnitOfWorkDep, user: CurrentUser, id: int) -> Resource:
    return await resource_actions.get(session=uow.session, id=id)


@router.post("/", response_model=Resource)
async def create_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_in: CreateResource
) -> Resource:
    return await resource_actions.create(
        session=uow.session, user=user, resource=resource_in
    )


class MergeRequest(BaseModel):
    resource_ids: list[int]


@router.post("/merge", response_model=Resource)
async def merge_resources_endpoint(
    *, uow: UnitOfWorkDep, user: CurrentUser, payload: MergeRequest
) -> Resource:
    """
    Merge multiple resources into one (STUB):
    repoint resource_ids[1:] -> resource_ids[0]
    """
    ids = payload.resource_ids
    # preserve order but drop duplicates
    unique_ids = list(dict.fromkeys(ids))
    if len(unique_ids) < 2:
        raise HTTPException(
            status_code=400, detail="Provide at least 2 unique resource IDs"
        )

    logger.info(
        "Merge requested by user=%s for resource_ids=%s",
        getattr(user, "sub", "<anon>"),
        unique_ids,
    )

    try:
        return await resource_actions.merge_resources(
            session=uow.session,
            user=user,
            resource_ids=unique_ids,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error while merging resources %s: %s", unique_ids, exc)
        raise HTTPException(status_code=500, detail="Internal error during merge")
