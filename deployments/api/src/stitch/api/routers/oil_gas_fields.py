import csv
import hashlib
import io
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from stitch.auth.permissions import (
    MERGE_CANDIDATE_CREATE,
    MERGE_CANDIDATE_READ,
    MERGE_CANDIDATE_REVIEW,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_PERMISSIONS,
    SOURCE_WRITE,
)

from stitch.api.entities import (
    OGFieldExportParams,
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
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceNotFoundError,
    ResourceIntegrityError,
    SourceIntegrityError,
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
    OGFieldName,
    OGFieldResource,
    OGFieldResourceView,
    OGFieldSource,
    OGFieldSourceValueView,
    OGFieldSourceView,
    OGFieldView,
    OGSISrcKey,
)


logger = logging.getLogger(__name__)

# Maximum number of rows returned by the CSV export endpoint. Requests that
# would exceed this limit receive a 400 response so the caller can narrow their
# filters. Chosen to bound memory and response time while covering most
# real-world filtered query sizes.
CSV_EXPORT_ROW_LIMIT = 10_000

# Ordered field names from OilGasFieldBase -- the columns that appear in the CSV
# after the ``id`` column. Keep in model-definition order so the export is
# predictable and matches the detail view.
_CSV_FIELD_NAMES: tuple[str, ...] = (
    "name",
    "country",
    "latitude",
    "longitude",
    "name_local",
    "state_province",
    "region",
    "basin",
    "owners",
    "operators",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "reservoir_formation",
    "discovery_year",
    "production_start_year",
    "fid_year",
    "field_status",
)

_CSV_HEADERS: tuple[str, ...] = (
    "id",
    *_CSV_FIELD_NAMES,
    *[f"{f}_source" for f in _CSV_FIELD_NAMES],
)


def _serialize_csv_value(value: Any) -> str:
    """Serialize a single field value to a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, list):
        # owners / operators: lists of Pydantic models -> JSON array string
        return json.dumps(
            [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        )
    return str(value)


def _items_to_csv(items: list[OGFieldListItemView]) -> str:
    """Render a list of resource list-item views as a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_HEADERS)
    for item in items:
        data = item.data
        row = [
            item.id,
            *[
                _serialize_csv_value(getattr(data, field, None))
                for field in _CSV_FIELD_NAMES
            ],
            *[item.provenance.get(field) or "" for field in _CSV_FIELD_NAMES],
        ]
        writer.writerow(row)
    return output.getvalue()


def _export_filename_hash(
    params: OGFieldExportParams,
    ls: frozenset[OGSISrcKey],
) -> str:
    """Return a 12-character hex hash that uniquely identifies this dataset.

    Two calls with the same filters AND the same licensed-source set produce the
    same hash, so users can tell at a glance whether two files match. Different
    licensing levels or different filter combinations produce different hashes.
    """
    canonical = json.dumps(
        {
            "filters": {
                k: str(v) for k, v in params.model_dump().items() if v is not None
            },
            "licensed_sources": sorted(ls),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


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
    "/export/csv",
    dependencies=[Depends(require_permissions(RESOURCE_READ))],
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV file download"},
        400: {"description": "Result set exceeds the export row limit"},
    },
)
async def export_resources_csv(
    *,
    uow: UnitOfWorkDep,
    _user: CurrentUser,
    claims: Claims,
    params: Annotated[OGFieldExportParams, Query()],
) -> Response:
    """Export the current resource list as a CSV file.

    Accepts the same filter and sort parameters as ``GET /``. When the result
    set would exceed ``CSV_EXPORT_ROW_LIMIT`` rows the endpoint returns HTTP
    400; callers should narrow their filters and retry.

    The ``Content-Disposition`` filename includes a short hash derived from the
    active filters and the caller's licensed-source set, so two users with
    different licensing levels can tell at a glance that their files may differ.
    """
    ls = licensed_sources(claims)
    items, total_count = await resource_actions.export(
        session=uow.session,
        params=params,
        licensed_sources=ls,
    )

    if total_count > CSV_EXPORT_ROW_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Export would return {total_count:,} resources, which exceeds the "
                f"{CSV_EXPORT_ROW_LIMIT:,}-row limit. "
                "Apply filters to narrow your results and try again."
            ),
        )

    file_hash = _export_filename_hash(params, ls)
    filename = f"stitch-export-{file_hash}.csv"
    csv_content = _items_to_csv(items)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    field: OGFieldName,
) -> list[OGFieldSourceValueView]:
    return await resource_actions.field_source_values(
        session=uow.session,
        id=id,
        field=field,
        licensed_sources=licensed_sources(claims),
    )


# Reordering rewrites the whole per-field override set, so a curator who cannot
# read every source could otherwise clobber rankings for sources they can't see.
# Require read access to *all* sources (not just this resource's) on top of write
# -- matching the curator role in Auth0 -- so the write always acts on a complete
# picture. (Scoped to this endpoint for now; other write actions to follow.)
@router.put(
    "/{id}/fields/{field}/sources/priority",
    response_model=list[OGFieldSourceValueView],
    dependencies=[
        Depends(require_permissions(RESOURCE_WRITE, *SOURCE_READ_PERMISSIONS))
    ],
)
async def set_field_source_priority(
    *,
    uow: UnitOfWorkDep,
    user: CurrentUser,
    claims: Claims,
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


@router.post(
    "/{id}/sources",
    response_model=OGFieldSourceView,
    dependencies=[Depends(require_permissions(RESOURCE_WRITE, SOURCE_WRITE))],
)
async def create_and_attach_source(
    *, uow: UnitOfWorkDep, user: CurrentUser, id: int, source: OGFieldSource
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
