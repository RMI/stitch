"""Bounded, per-resource entity-linkage matching.

This is the memory-safe matcher. Rather than loading every resource into memory
and grouping it there (the original whole-dataset pass), this module matches one
resource at a time:

1. fetch the seed resource's detail (name + country);
2. search the API for a *superset* of same-name candidates using the
   case-insensitive ``q`` (ILIKE) filter -- the API's ``name`` filter is exact
   and case-sensitive, so we widen with ``q`` and re-narrow here to preserve the
   existing casefold+strip blocking (see STIT-573; a DB-side normalized-name
   match is a tracked follow-up);
3. confirm each same-name candidate shares the seed's (normalized) country;
4. if two or more resources survive, that block is a merge candidate.

Peak memory is bounded to a single resource's candidate block, independent of
total dataset size. The bulk driver (:func:`link_all`) streams resource ids one
page at a time, so it never materializes the whole table either.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.entities import (
    BulkLinkResponse,
    ResourceLinkResult,
    normalize_country,
    normalize_name,
)
from stitch.entity_linkage.errors import StitchAPIError

logger = logging.getLogger(__name__)

# A 4xx from create-merge-candidate is an expected, non-fatal outcome during a
# run: the API rejects a duplicate fingerprint (a candidate already exists) or a
# resource that has already been merged. We skip those rather than aborting.
_ALREADY_HANDLED_STATUS = 400


def merge_fingerprint(resource_ids: Sequence[int]) -> str:
    """Sorted, de-duplicated id key.

    Mirrors ``_fingerprint`` in the API's ``merge_candidate_actions`` so we can
    recognise groups that already exist in the candidate queue without a POST.
    """
    return ":".join(str(i) for i in sorted(set(resource_ids)))


async def find_match_group_for_resource(
    client: StitchApiClient,
    resource_id: int,
) -> list[int]:
    """Return the sorted id block ``resource_id`` merges into, or ``[]``.

    The block is every resource that shares the seed's normalized name *and*
    normalized country (including the seed). A block of fewer than two resources
    is not a merge candidate and yields ``[]``.
    """
    seed = await client.get_oil_gas_field_detail(resource_id)
    seed_name = normalize_name(seed.name)
    seed_country = normalize_country(seed.country)
    if seed_name is None or seed_country is None:
        return []

    # Stream the case-insensitive ``q`` superset a page at a time and keep only
    # exact normalized-name matches, so peak memory is bounded by the same-name
    # block rather than the (potentially large) ILIKE substring superset.
    #
    # Search on the *normalized* name: ``q`` is a literal ILIKE ``%term%``, so a
    # raw name with surrounding whitespace would exclude clean-named duplicates
    # (and vice versa), missing exactly the whitespace variants this blocking is
    # meant to catch. ``seed_name`` is stripped + casefolded; ILIKE is already
    # case-insensitive, so the casefold is harmless and the strip is what matters.
    same_name_ids: set[int] = set()
    async for candidate in client.iter_oil_gas_fields(q=seed_name):
        if candidate.normalized_name == seed_name:
            same_name_ids.add(candidate.id)
    # The seed always belongs to its own block even if the list universe omits it.
    same_name_ids.add(resource_id)

    matched: list[int] = []
    for candidate_id in sorted(same_name_ids):
        detail = (
            seed
            if candidate_id == resource_id
            else (await client.get_oil_gas_field_detail(candidate_id))
        )
        if normalize_country(detail.country) == seed_country:
            matched.append(detail.id)

    matched = sorted(set(matched))
    return matched if len(matched) >= 2 else []


async def _submit_group(
    client: StitchApiClient,
    resource_ids: list[int],
    *,
    apply_merges: bool,
    known_existing: set[str] | None,
) -> tuple[bool, bool]:
    """Create a merge candidate for ``resource_ids``. Returns ``(created, skipped)``.

    On a dry run (``apply_merges`` false) nothing is created and nothing is
    skipped. When applying, ``known_existing`` (optional) is a set of fingerprints
    already present in the candidate queue; a match there is skipped without a
    POST.
    """
    if not apply_merges:
        return (False, False)
    if known_existing is not None and merge_fingerprint(resource_ids) in known_existing:
        return (False, True)
    try:
        await client.create_merge_candidate(resource_ids=resource_ids)
    except StitchAPIError as exc:
        if exc.status_code == _ALREADY_HANDLED_STATUS:
            return (False, True)
        raise
    return (True, False)


async def link_resource(
    client: StitchApiClient,
    resource_id: int,
    *,
    apply_merges: bool,
    known_existing: set[str] | None = None,
) -> ResourceLinkResult:
    """Match a single resource and optionally submit its merge candidate."""
    matched = await find_match_group_for_resource(client, resource_id)
    if not matched:
        return ResourceLinkResult(
            resource_id=resource_id,
            matched_ids=[],
            merge_candidate_created=False,
            skipped_existing=False,
        )
    created, skipped = await _submit_group(
        client,
        matched,
        apply_merges=apply_merges,
        known_existing=known_existing,
    )
    return ResourceLinkResult(
        resource_id=resource_id,
        matched_ids=matched,
        merge_candidate_created=created,
        skipped_existing=skipped,
    )


async def _existing_fingerprints(client: StitchApiClient) -> set[str]:
    """Fingerprints of merge candidates already in the queue."""
    existing = await client.list_merge_candidates()
    fingerprints: set[str] = set()
    for candidate in existing:
        resource_ids = candidate.get("resource_ids")
        if isinstance(resource_ids, list):
            fingerprints.add(merge_fingerprint(resource_ids))
    return fingerprints


async def link_all(
    client: StitchApiClient,
    *,
    apply_merges: bool,
    page_size: int,
    initiated_by: str,
) -> BulkLinkResponse:
    """Run the bounded matcher over every resource, streaming ids page by page.

    Groups are de-duplicated by fingerprint across the run, so each block is
    submitted at most once even though every member rediscovers it. Members of an
    already-formed block are skipped without re-searching.
    """
    # Only needed when we will actually POST; skip the (currently unpaginated)
    # candidate-list fetch entirely on a dry run.
    known_existing = await _existing_fingerprints(client) if apply_merges else None

    groups_by_fingerprint: dict[str, list[int]] = {}
    processed_ids: set[int] = set()
    resources_scanned = 0
    created = 0
    skipped = 0
    failed = 0

    async for candidate in client.iter_oil_gas_fields(page_size=page_size):
        resources_scanned += 1
        if candidate.id in processed_ids:
            continue

        # Isolate each resource: a transient error already exhausted the shared
        # client's retries, or the API rejected this one resource. Skipping and
        # counting it keeps a multi-hour run alive instead of aborting on a
        # single bad resource. Only network/API errors are caught -- a
        # programming error still propagates so real bugs surface.
        try:
            matched = await find_match_group_for_resource(client, candidate.id)
            if not matched:
                continue

            processed_ids.update(matched)
            fingerprint = merge_fingerprint(matched)
            if fingerprint in groups_by_fingerprint:
                continue
            groups_by_fingerprint[fingerprint] = matched

            was_created, was_skipped = await _submit_group(
                client,
                matched,
                apply_merges=apply_merges,
                known_existing=known_existing,
            )
        except (StitchAPIError, httpx.HTTPError, OSError) as exc:
            failed += 1
            logger.warning("Skipping resource %s after error: %s", candidate.id, exc)
            continue

        if was_created:
            created += 1
        elif was_skipped:
            skipped += 1

    return BulkLinkResponse(
        initiated_by=initiated_by,
        apply_merges=apply_merges,
        resources_scanned=resources_scanned,
        match_groups=list(groups_by_fingerprint.values()),
        merge_candidates_created=created,
        merge_candidates_skipped=skipped,
        resources_failed=failed,
    )
