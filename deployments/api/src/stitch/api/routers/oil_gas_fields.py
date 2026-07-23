import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from stitch.auth.permissions import (
    MERGE_CANDIDATE_CREATE,
    MERGE_CANDIDATE_READ,
    MERGE_CANDIDATE_REVIEW,
    RESOURCE_READ,
    RESOURCE_WRITE,
)

from stitch.api.entities import (
    OGFieldFilterOptionsParams,
    OGFieldFilterOptionsResponse,
    MergeCandidateCreateRequest,
    MergeCandidateDetailView,
    MergeCandidateReviewRequest,
    MergeCandidateView,
    OGFieldQueryParams,
    PaginatedResponse,
    SetFieldPriorityRequest,
)

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import merge_candidate_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceNotFoundError,
    ResourceIntegrityError,
)
from stitch.api.auth import Claims, CurrentUser, require_permissions
from stitch.api.db.utils import (
    resource_to_view,
    resource_to_detail_view,
)
from stitch.api.permissions import licensed_sources

from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldListItemView,
    OGFieldResource,
    OGFieldResourceView,
    OGFieldSourceValueView,
    OGFieldView,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/oil-gas-fields",
    tags=["oil_gas_fields"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", dependencies=[Depends(require_permissions(RESOURCE_READ))])
async def get_all_resources(
    *,
    uow: UnitOfWorkDep,
    _user: CurrentUser,
    claims: Claims,
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldListItemView]:
    items, total_count = await resource_actions.query(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(claims),
    )
    return PaginatedResponse(
        items=items,
        total_count=total_count,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/filter-options", response_model=OGFieldFilterOptionsResponse)
async def get_resource_filter_options(
    *,
    uow: UnitOfWorkDep,
    _user: CurrentUser,
    claims: Claims,
    params: Annotated[OGFieldFilterOptionsParams, Query()],
) -> OGFieldFilterOptionsResponse:
    values = await resource_actions.filter_options(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(claims),
    )
    return OGFieldFilterOptionsResponse(field=params.field, values=values)


@router.get(
    "/merge-candidates",
    response_model=list[MergeCandidateView],
    dependencies=[Depends(require_permissions(MERGE_CANDIDATE_READ))],
)
async def list_merge_candidates(
    *, uow: UnitOfWorkDep, _user: CurrentUser
) -> list[MergeCandidateView]:
    return await merge_candidate_actions.list_merge_candidates(session=uow.session)


@router.get(
    "/merge-candidates/{id}",
    response_model=MergeCandidateDetailView,
    dependencies=[Depends(require_permissions(MERGE_CANDIDATE_READ))],
)
async def get_merge_candidate(
    *, uow: UnitOfWorkDep, _user: CurrentUser, claims: Claims, id: int
) -> MergeCandidateDetailView:
    try:
        return await merge_candidate_actions.get_merge_candidate(
            session=uow.session,
            candidate_id=id,
            licensed_sources=licensed_sources(claims),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/merge-candidates",
    response_model=MergeCandidateView,
    dependencies=[Depends(require_permissions(MERGE_CANDIDATE_CREATE))],
)
async def create_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    request: MergeCandidateCreateRequest,
) -> MergeCandidateView:
    logger.info(
        "Merge candidate requested by user=%s for resource_ids=%s",
        getattr(user, "sub", "<anon>"),
        request.resource_ids,
    )

    try:
        return await merge_candidate_actions.create_merge_candidate(
            session=uow.session,
            user=user,
            request=request,
        )
    except (InvalidActionError, ResourceIntegrityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Error while creating merge candidate for resource_ids %s: %s",
            request.resource_ids,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error during merge candidate creation",
        )


@router.post(
    "/merge-candidates/{id}/approve",
    response_model=MergeCandidateView,
    dependencies=[Depends(require_permissions(MERGE_CANDIDATE_REVIEW))],
)
async def approve_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    try:
        return await merge_candidate_actions.approve_merge_candidate(
            session=uow.session,
            user=user,
            candidate_id=id,
            request=request,
        )
    except (InvalidActionError, ResourceIntegrityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error while approving merge candidate %s: %s", id, exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error during merge candidate approval",
        )


@router.post(
    "/merge-candidates/{id}/deny",
    response_model=MergeCandidateView,
    dependencies=[Depends(require_permissions(MERGE_CANDIDATE_REVIEW))],
)
async def deny_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    try:
        return await merge_candidate_actions.deny_merge_candidate(
            session=uow.session,
            user=user,
            candidate_id=id,
            request=request,
        )
    except (InvalidActionError, ResourceIntegrityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error while denying merge candidate %s: %s", id, exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error during merge candidate denial",
        )


@router.get(
    "/{id}",
    response_model=OGFieldView,
    dependencies=[Depends(require_permissions(RESOURCE_READ))],
)
async def get_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, claims: Claims, id: int
) -> OGFieldView:
    res: OGFieldResource = await resource_actions.get(
        session=uow.session, id=id, licensed_sources=licensed_sources(claims)
    )
    return resource_to_view(resource=res)


@router.get(
    "/{id}/detail",
    response_model=OGFieldDetailView,
    dependencies=[Depends(require_permissions(RESOURCE_READ))],
)
async def get_resource_detail(
    *, uow: UnitOfWorkDep, user: CurrentUser, claims: Claims, id: int
) -> OGFieldDetailView:
    res: OGFieldResource = await resource_actions.get(
        session=uow.session, id=id, licensed_sources=licensed_sources(claims)
    )
    return resource_to_detail_view(resource=res)


@router.get(
    "/{id}/fields/{field}/sources",
    response_model=list[OGFieldSourceValueView],
    dependencies=[Depends(require_permissions(RESOURCE_READ))],
)
async def get_field_source_values(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    claims: Claims,
    id: int,
    field: str,
) -> list[OGFieldSourceValueView]:
    return await resource_actions.field_source_values(
        session=uow.session,
        id=id,
        field=field,
        licensed_sources=licensed_sources(claims),
    )


@router.put(
    "/{id}/fields/{field}/sources/priority",
    response_model=list[OGFieldSourceValueView],
    dependencies=[Depends(require_permissions(RESOURCE_WRITE))],
)
async def set_field_source_priority(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    claims: Claims,
    id: int,
    field: str,
    request: SetFieldPriorityRequest,
) -> list[OGFieldSourceValueView]:
    try:
        return await resource_actions.set_field_source_priority(
            session=uow.session,
            user=user,
            id=id,
            field=field,
            ordered_source_pks=request.ordered_source_pks,
            licensed_sources=licensed_sources(claims),
        )
    except (InvalidActionError, ResourceIntegrityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Error setting field-source priority for resource %s field %s: %s",
            id,
            field,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error while setting field source priority",
        )


@router.post(
    "/",
    response_model=OGFieldResourceView,
    dependencies=[Depends(require_permissions(RESOURCE_WRITE))],
)
async def create_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_in: OGFieldResource
) -> OGFieldResourceView:
    return await resource_actions.create(
        session=uow.session, user=user, resource=resource_in
    )
