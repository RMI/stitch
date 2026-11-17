import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from stitch.api.entities import (
    LinkAllResponse,
    OGFieldFilterOptionsResponse,
    MergeCandidateCreateRequest,
    MergeCandidateDetailView,
    MergeCandidatePage,
    MergeCandidateQueryParams,
    MergeCandidateReviewRequest,
    MergeCandidateView,
    OGFieldFilterParams,
    OGFieldQueryParams,
    PaginatedResponse,
    SetFieldPriorityRequest,
)

from stitch.api.db import link_actions
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import merge_candidate_actions
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceNotFoundError,
    ResourceIntegrityError,
    SourceIntegrityError,
)
from stitch.api._auth import (
    MERGE_CANDIDATE_CREATE,
    MERGE_CANDIDATE_READ,
    MERGE_CANDIDATE_REVIEW,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_PERMISSIONS,
    SOURCE_WRITE,
    AuthenticatedUser,
    licensed_sources,
    require_user,
)
from stitch.api.db.utils import (
    resource_to_view,
    resource_to_detail_view,
)

from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldListItemView,
    OGFieldName,
    OGFieldResource,
    OGFieldResourceView,
    OGFieldSource,
    OGFieldSourceValueView,
    OGFieldSourceView,
    OGFieldView,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/oil-gas-fields",
    tags=["oil_gas_fields"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_resources(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(RESOURCE_READ))],
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldListItemView]:
    items, total_count = await resource_actions.query(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(user.claims),
    )
    return PaginatedResponse(
        items=items,
        total_count=total_count,
        page=params.page,
        page_size=params.page_size,
    )


# Must stay above GET /{id}: Starlette matches routes in declaration order, so a
# later static path would be swallowed by the id route.
@router.get("/filter-options", response_model=OGFieldFilterOptionsResponse)
async def get_resource_filter_options(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user())],
    params: Annotated[OGFieldFilterParams, Query()],
) -> OGFieldFilterOptionsResponse:
    opts = await resource_actions.filter_options(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(user.claims),
    )
    return OGFieldFilterOptionsResponse(**opts)


@router.get(
    "/merge-candidates",
    response_model=MergeCandidatePage,
)
async def list_merge_candidates(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_READ))],
    params: Annotated[MergeCandidateQueryParams, Query()],
) -> MergeCandidatePage:
    return await merge_candidate_actions.list_merge_candidates(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(user.claims),
    )


@router.get(
    "/merge-candidates/{id}",
    response_model=MergeCandidateDetailView,
)
async def get_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_READ))],
    id: int,
) -> MergeCandidateDetailView:
    try:
        return await merge_candidate_actions.get_merge_candidate(
            session=uow.session,
            candidate_id=id,
            licensed_sources=licensed_sources(user.claims),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/merge-candidates",
    response_model=MergeCandidateView,
)
async def create_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_CREATE))],
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
    "/merge-candidates/link-all",
    response_model=LinkAllResponse,
)
async def link_all_merge_candidates(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_CREATE))],
    apply_merges: bool = True,
) -> LinkAllResponse:
    """Queue every group of duplicate resources for review."""
    groups = await link_actions.match(
        session=uow.session,
        licensed_sources=licensed_sources(user.claims),
    )
    existing = await merge_candidate_actions.existing_candidate_resource_sets(
        session=uow.session
    )
    new_groups = [group for group in groups if frozenset(group) not in existing]

    if apply_merges:
        await merge_candidate_actions.create_merge_candidates_bulk(
            session=uow.session,
            user=user,
            groups=new_groups,
        )
        await uow.commit()

    return LinkAllResponse(
        apply_merges=apply_merges,
        match_groups=[list(group) for group in groups],
        merge_candidates_created=len(new_groups) if apply_merges else 0,
        merge_candidates_skipped=len(groups) - len(new_groups),
    )


@router.post(
    "/merge-candidates/{id}/approve",
    response_model=MergeCandidateView,
)
async def approve_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_REVIEW))],
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
)
async def deny_merge_candidate(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(MERGE_CANDIDATE_REVIEW))],
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


def _requested_resource_id(requested_id: int, resolved: OGFieldResource) -> int | None:
    """The originally-requested id when the resolver returned a different resource
    (i.e. the request was redirected through a merge); ``None`` otherwise."""
    return requested_id if resolved.id != requested_id else None


@router.get(
    "/{id}",
    response_model=OGFieldView,
)
async def get_resource(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(RESOURCE_READ))],
    id: int,
) -> OGFieldView:
    res: OGFieldResource = await resource_actions.get_resolved(
        session=uow.session, id=id, licensed_sources=licensed_sources(user.claims)
    )
    return resource_to_view(
        resource=res, requested_resource_id=_requested_resource_id(id, res)
    )


@router.get(
    "/{id}/detail",
    response_model=OGFieldDetailView,
)
async def get_resource_detail(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(RESOURCE_READ))],
    id: int,
) -> OGFieldDetailView:
    res: OGFieldResource = await resource_actions.get_resolved(
        session=uow.session, id=id, licensed_sources=licensed_sources(user.claims)
    )
    return resource_to_detail_view(
        resource=res, requested_resource_id=_requested_resource_id(id, res)
    )


@router.get(
    "/{id}/fields/{field}/sources",
    response_model=list[OGFieldSourceValueView],
)
async def get_field_source_values(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(RESOURCE_READ))],
    id: int,
    field: OGFieldName,
) -> list[OGFieldSourceValueView]:
    return await resource_actions.field_source_values(
        session=uow.session,
        id=id,
        field=field,
        licensed_sources=licensed_sources(user.claims),
    )


# Reordering rewrites the whole per-field override set, so a curator who cannot
# read every source could otherwise clobber rankings for sources they can't see.
# Require read access to *all* sources (not just this resource's) on top of write
# -- matching the curator role in Auth0 -- so the write always acts on a complete
# picture. (Scoped to this endpoint for now; other write actions to follow.)
@router.put(
    "/{id}/fields/{field}/sources/priority",
    response_model=list[OGFieldSourceValueView],
)
async def set_field_source_priority(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_user(RESOURCE_WRITE, *SOURCE_READ_PERMISSIONS)),
    ],
    id: int,
    field: OGFieldName,
    request: SetFieldPriorityRequest,
) -> list[OGFieldSourceValueView]:
    try:
        return await resource_actions.set_field_source_priority(
            session=uow.session,
            user=user,
            id=id,
            field=field,
            ordered_source_pks=request.ordered_source_pks,
            licensed_sources=licensed_sources(user.claims),
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
)
async def create_resource(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(RESOURCE_WRITE))],
    resource_in: OGFieldResource,
) -> OGFieldResourceView:
    return await resource_actions.create(
        session=uow.session, user=user, resource=resource_in
    )


@router.post(
    "/{id}/sources",
    response_model=OGFieldSourceView,
)
async def create_and_attach_source(
    *,
    uow: UnitOfWorkDep,
    user: Annotated[
        AuthenticatedUser, Depends(require_user(RESOURCE_WRITE, SOURCE_WRITE))
    ],
    id: int,
    source: OGFieldSource,
) -> OGFieldSourceView:
    """Create a new source and attach it to resource ``id`` in one step.

    The source body must not carry an ``id`` (it is always created). Requires
    both ``source:write`` (creating the source) and ``resource:write``
    (managing the attachment).
    """
    try:
        return await og_field_source_actions.create_and_attach_source(
            session=uow.session, user=user, source=source, resource_id=id
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ResourceIntegrityError, SourceIntegrityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Error while creating and attaching source to resource %s: %s", id, exc
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error during source creation and attachment",
        )
