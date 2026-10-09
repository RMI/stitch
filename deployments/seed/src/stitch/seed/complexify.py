"""Post-create complexifier for perf-test / integration datasets.

After the base resources are seeded, optionally drive the public write API to
add the two remaining kinds of complexity the coalescing layer cares about:

* **Field-specific priority overrides** — re-rank a multi-source resource's
  sources for one field (`PUT /{id}/fields/{field}/sources/priority`), exercising
  the two-tier per-field ranking.
* **Merges** — approve a merge candidate over a pair of resources
  (`POST /merge-candidates/{id}/approve`), producing repointed resources.

Everything is driven by a caller-supplied seeded RNG so the resulting dataset is
reproducible across branches. All knobs default to off in ``config`` — this pass
is a no-op unless ``override_prob``/``merge_prob`` are set.

Notes:
* An override only lands on a resource with >=2 sources for the chosen field, so
  the *realized* override count is conditioned on the multi-source fraction of the
  dataset — it is not simply ``override_prob * len(resource_ids)``. The summary
  log below reports selected/eligible/applied so a thin result can be spotted.
* These three write flows (field-sources GET, priority PUT, merge approve) are not
  on the public ``AsyncStitchClient`` surface, so we call ``client._request_json``
  directly. That couples this seed-only tool to a client internal; if it changes,
  prefer adding public client helpers over widening this coupling.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from stitch.client import AsyncStitchClient


logger = logging.getLogger("stitch.seed")

# Fields to consider for an override. `name`/`country` are required on every
# source, so a multi-source resource always has >=2 candidates for them; the
# optional ones add variety when present.
_OVERRIDE_FIELDS: tuple[str, ...] = (
    "name",
    "country",
    "basin",
    "region",
    "field_status",
    "operators",
)


async def _field_source_pks(
    client: AsyncStitchClient, resource_id: int, field: str
) -> list[int]:
    """The source pks that carry a value for ``field`` (winner-first), or []."""
    try:
        rows = await client._request_json(
            method="GET",
            path=f"/oil-gas-fields/{resource_id}/fields/{field}/sources",
            operation=f"GET /oil-gas-fields/{resource_id}/fields/{field}/sources",
        )
    except Exception:
        logger.warning(
            "Complexify: field-sources lookup failed for resource=%s field=%s",
            resource_id,
            field,
            exc_info=True,
        )
        return []
    if not isinstance(rows, list):
        return []
    return [
        row["source_id"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), int)
    ]


async def _apply_overrides(
    client: AsyncStitchClient,
    resource_ids: list[int],
    *,
    rng: random.Random,
    override_prob: float,
) -> int:
    # selected = drawn by the probability gate; eligible = had a field with >=2
    # candidates (a single-source resource legitimately has none); applied = PUT
    # succeeded; failed = PUT raised. Only `failed` is an error worth surfacing.
    selected = eligible = applied = failed = 0
    for resource_id in resource_ids:
        if rng.random() >= override_prob:
            continue
        selected += 1
        # Try fields in a shuffled order; take the first with >=2 candidates.
        fields = list(_OVERRIDE_FIELDS)
        rng.shuffle(fields)
        for field in fields:
            pks = await _field_source_pks(client, resource_id, field)
            if len(pks) < 2:
                continue
            eligible += 1
            new_order = pks[:]
            rng.shuffle(new_order)
            if new_order == pks:
                new_order.reverse()  # guarantee an actual re-rank
            try:
                await client._request_json(
                    method="PUT",
                    path=f"/oil-gas-fields/{resource_id}/fields/{field}/sources/priority",
                    operation=(
                        f"PUT /oil-gas-fields/{resource_id}/fields/{field}/sources/priority"
                    ),
                    json={"ordered_source_pks": new_order},
                )
                applied += 1
            except Exception:
                failed += 1
                logger.warning(
                    "Complexify: override PUT failed for resource=%s field=%s",
                    resource_id,
                    field,
                    exc_info=True,
                )
            break
    logger.info(
        "Complexify: applied %d field-priority override(s) "
        "[selected=%d eligible=%d failed=%d]",
        applied,
        selected,
        eligible,
        failed,
    )
    if failed:
        logger.warning("Complexify: %d override PUT(s) failed (see warnings)", failed)
    elif selected and eligible == 0:
        logger.warning(
            "Complexify: override_prob selected %d resource(s) but none had a "
            "multi-source field to re-rank — enable SEED_MULTI_SOURCE_PROB for "
            "overrides to take effect",
            selected,
        )
    return applied


async def _apply_merges(
    client: AsyncStitchClient,
    resource_ids: list[int],
    *,
    rng: random.Random,
    merge_prob: float,
) -> int:
    eligible = [rid for rid in resource_ids if rng.random() < merge_prob]
    pairs = len(eligible) // 2
    merged = failed = 0
    for i in range(0, len(eligible) - 1, 2):
        pair = [eligible[i], eligible[i + 1]]
        try:
            candidate: dict[str, Any] = await client.create_merge_candidate(pair)
            candidate_id = candidate.get("id")
            if not isinstance(candidate_id, int):
                failed += 1
                logger.warning(
                    "Complexify: merge candidate for pair=%s returned no id", pair
                )
                continue
            await client._request_json(
                method="POST",
                path=f"/oil-gas-fields/merge-candidates/{candidate_id}/approve",
                operation=(
                    f"POST /oil-gas-fields/merge-candidates/{candidate_id}/approve"
                ),
                json={},
            )
            merged += 1
        except Exception:
            failed += 1
            logger.warning("Complexify: merge failed for pair=%s", pair, exc_info=True)
    logger.info(
        "Complexify: approved %d merge(s) [pairs_attempted=%d failed=%d]",
        merged,
        pairs,
        failed,
    )
    if failed:
        logger.warning("Complexify: %d merge(s) failed (see warnings)", failed)
    return merged


async def complexify(
    client: AsyncStitchClient,
    resource_ids: list[int],
    *,
    rng: random.Random,
    override_prob: float,
    merge_prob: float,
) -> None:
    """Apply field-priority overrides then merges to the created resources."""
    if override_prob > 0.0:
        await _apply_overrides(
            client, resource_ids, rng=rng, override_prob=override_prob
        )
    if merge_prob > 0.0:
        await _apply_merges(client, resource_ids, rng=rng, merge_prob=merge_prob)
