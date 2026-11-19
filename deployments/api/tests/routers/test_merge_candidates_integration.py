"""Integration tests for the merge-candidate endpoints (real SQLite)."""

from collections.abc import Sequence
from datetime import datetime, timezone
from unittest.mock import patch

from httpx import AsyncClient
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.auth import TokenClaims
from stitch.auth.permissions import (
    MERGE_CANDIDATE_CREATE,
    MERGE_CANDIDATE_READ,
    RESOURCE_READ,
    SOURCE_READ_GEM,
    SOURCE_READ_PREFIX,
)

from tests.factories import ResourceCreateFactory
from stitch.api.auth import get_token_claims
from stitch.api.db import link_actions
from stitch.api.db.config import UnitOfWork
from stitch.api.db.model import (
    MembershipModel,
    MergeCandidateModel,
    OGFieldResourceSourcePriority,
)
from stitch.api.main import app
from stitch.api.db.read_model.permissions import PUBLIC_SOURCES
from stitch.ogsi.model import OGFieldResource, OGFieldSource


async def _create_resource(
    client: AsyncClient, fact: ResourceCreateFactory, name: str
) -> int:
    payload = fact(name=name).model_dump(mode="json")
    resp = await client.post("/oil-gas-fields/", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _create_resource_with_sources(
    client: AsyncClient,
    res_factory,
    sources: Sequence[OGFieldSource],
) -> int:
    """POST a resource built from explicit source entities (controlled values)."""
    model: OGFieldResource = res_factory.build(
        id=None,
        source_data=list(sources),
        constituents=frozenset(),
        repointed_to=None,
        view=None,
        provenance={},
    )
    resp = await client.post("/oil-gas-fields/", json=model.model_dump(mode="json"))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _create_candidate(client: AsyncClient, resource_ids: list[int]) -> int:
    resp = await client.post(
        "/oil-gas-fields/merge-candidates",
        json={"resource_ids": resource_ids},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


class TestMergeCandidateDetailIntegration:
    @pytest.mark.anyio
    async def test_detail_includes_compare_tagged_with_resource_ids(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        candidate_id = await _create_candidate(integration_client, [id_a, id_b])

        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "PENDING"
        assert body["resource_ids"] == [id_a, id_b]
        # `resources` detail objects were dropped; `compare` carries everything.
        assert "resources" not in body

        # `compare`: one entry per field; each value tagged with its source and
        # the resource it is attached to (source_id, value, priority, resource_id).
        compare = {c["field"]: c for c in body["compare"]}
        name_cmp = compare["name"]
        for entry in name_cmp["values"]:
            assert {
                "source",
                "source_id",
                "value",
                "priority",
                "resource_id",
            } <= set(entry)

        # The two resources resolve `name` to different values -> different.
        assert name_cmp["status"] == "different"
        assert name_cmp["values"][0]["value"] == "Ghawar"  # winner-first by priority
        # each source is attributed to the resource it is attached to
        rmi_by_resource = {
            (v["resource_id"], v["value"])
            for v in name_cmp["values"]
            if v["source"] == "rmi"
        }
        assert {(id_a, "Ghawar"), (id_b, "Burgan")} <= rmi_by_resource

    @pytest.mark.anyio
    async def test_detail_after_approve_is_live_null_shell(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        candidate_id = await _create_candidate(integration_client, [id_a, id_b])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_id}/approve",
            json={"review_notes": "ok"},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["merged_resource_id"] is not None

        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "APPROVED"
        assert body["merged_resource_id"] is not None
        assert body["resource_ids"] == [id_a, id_b]
        assert "resources" not in body
        # Live compute: originals are repointed with memberships INACTIVE, so no
        # sources survive -> both resources are null everywhere, so every field
        # matches with no values. (Freeze snapshot is deferred.)
        for entry in body["compare"]:
            assert entry["status"] == "match"
            assert entry["values"] == []

    @pytest.mark.anyio
    async def test_per_resource_override_is_reverted_by_merge(
        self,
        integration_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        og_field_resource_factory,
        source_maker,
    ):
        # Resource A carries RMI "RMI-name" (default winner) and GEM "GEM-name".
        id_a = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [
                source_maker(source="rmi", managed=False, name="RMI-name"),
                source_maker(source="gem", managed=False, name="GEM-name"),
            ],
        )
        id_b = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [source_maker(source="rmi", managed=False, name="B-name")],
        )

        # Override A's ordering so GEM outranks RMI for the NAME field -> A's
        # coalesced name flips. Overrides are per-field, per-source-record now, so
        # curate GEM's record for `name`.
        async with integration_session_factory() as session:
            gem_pk = await session.scalar(
                select(MembershipModel.source_pk).where(
                    MembershipModel.resource_id == id_a,
                    MembershipModel.source == "gem",
                )
            )
            session.add(
                OGFieldResourceSourcePriority(
                    resource_id=id_a,
                    source="gem",
                    source_pk=gem_pk,
                    colname="name",
                    priority=0,
                    created_by_id=1,
                    last_updated_by_id=1,
                )
            )
            await session.commit()

        # A's coalesced value reflects the override: its name resolves to GEM's.
        detail_a = await integration_client.get(f"/oil-gas-fields/{id_a}/detail")
        assert detail_a.status_code == 200, detail_a.text
        assert detail_a.json()["data"]["name"] == "GEM-name"  # override in effect

        candidate_id = await _create_candidate(integration_client, [id_a, id_b])
        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # A resolves `name` to its override value (GEM-name), B to B-name, so the
        # resources differ. `values` is winner-first by default priority (RMI),
        # and both of A's sources are attributed to resource A.
        name_cmp = next(c for c in body["compare"] if c["field"] == "name")
        assert name_cmp["status"] == "different"
        assert name_cmp["values"][0]["value"] == "RMI-name"
        a_values = {
            (v["source"], v["value"])
            for v in name_cmp["values"]
            if v["resource_id"] == id_a
        }
        assert {("rmi", "RMI-name"), ("gem", "GEM-name")} <= a_values

        # Approving materializes the reset: the merged resource has no override
        # rows and resolves `name` in default order (RMI), dropping the override.
        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_id}/approve",
        )
        assert approve.status_code == 200, approve.text
        merged_id = approve.json()["merged_resource_id"]
        assert merged_id is not None

        merged = await integration_client.get(f"/oil-gas-fields/{merged_id}/detail")
        assert merged.status_code == 200, merged.text
        assert merged.json()["data"]["name"] == "RMI-name"

        async with integration_session_factory() as session:
            overrides = (
                await session.execute(
                    select(OGFieldResourceSourcePriority).where(
                        OGFieldResourceSourcePriority.resource_id == merged_id
                    )
                )
            ).all()
        assert overrides == []

    @pytest.mark.anyio
    async def test_overlapping_approval_reroutes_pending_candidate(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # Two overlapping candidates share resource A. Approving A+B -> D must
        # repoint the pending A+C to D+C: it stays PENDING and its comparison now
        # shows D's live values (STIT-418 AC 3).
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])
        candidate_ac = await _create_candidate(integration_client, [id_a, id_c])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
            json={"review_notes": "ok"},
        )
        assert approve.status_code == 200, approve.text
        merged_d = approve.json()["merged_resource_id"]
        assert merged_d is not None

        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # A(18) is gone; the candidate now compares D against C, still PENDING.
        assert body["status"] == "PENDING"
        assert body["resource_ids"] == [merged_d, id_c]

        name_cmp = next(c for c in body["compare"] if c["field"] == "name")
        value_resource_ids = {v["resource_id"] for v in name_cmp["values"]}
        # No value is attributed to the merged-away original...
        assert id_a not in value_resource_ids
        # ...D's live values are shown (not a null shell)...
        assert merged_d in value_resource_ids
        # ...alongside C's own value.
        assert (id_c, "Safaniya") in {
            (v["resource_id"], v["value"]) for v in name_cmp["values"]
        }

        # The re-routed candidate is now approvable (no already-merged 400).
        approve_ac = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}/approve",
        )
        assert approve_ac.status_code == 200, approve_ac.text
        assert approve_ac.json()["merged_resource_id"] is not None

    @pytest.mark.anyio
    async def test_already_merged_error_names_ids_not_repr(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # Once A is merged away, referencing it again is rejected with an id-based
        # message -- no ORM repr() leak (`object at 0x...`).
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
        )
        assert approve.status_code == 200, approve.text
        merged_d = approve.json()["merged_resource_id"]

        resp = await integration_client.post(
            "/oil-gas-fields/merge-candidates",
            json={"resource_ids": [id_a, id_c]},
        )
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert f"resource {id_a} is now resource {merged_d}" in detail
        assert "object at 0x" not in detail

    @pytest.mark.anyio
    async def test_two_overlapping_candidates_collapse_to_one(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # A+C and B+C both re-route to D+C when A+B is approved. They become the
        # same proposal, so exactly one survives (the earlier-created candidate).
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ac = await _create_candidate(integration_client, [id_a, id_c])
        candidate_bc = await _create_candidate(integration_client, [id_b, id_c])
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
        )
        assert approve.status_code == 200, approve.text
        merged_d = approve.json()["merged_resource_id"]

        survivor = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}"
        )
        assert survivor.status_code == 200, survivor.text
        assert survivor.json()["status"] == "PENDING"
        assert survivor.json()["resource_ids"] == [merged_d, id_c]

        dropped = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_bc}"
        )
        assert dropped.status_code == 404, dropped.text

    @pytest.mark.anyio
    async def test_pairwise_triangle_collapses_over_sequential_merges(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # Entity linkage emits pairwise candidates, so a 3-cluster {A,B,C} yields
        # A+B, B+C, and A+C. Merging the cluster edge by edge must collapse the
        # redundant third candidate rather than leave it as a stale dead end.
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])
        candidate_bc = await _create_candidate(integration_client, [id_b, id_c])
        candidate_ac = await _create_candidate(integration_client, [id_a, id_c])

        # Merge A+B -> D. Both B+C and A+C re-route to D+C (the same proposal), so
        # the later-created A+C is dropped and B+C survives.
        approve_ab = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
        )
        assert approve_ab.status_code == 200, approve_ab.text
        merged_d = approve_ab.json()["merged_resource_id"]

        dropped = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}"
        )
        assert dropped.status_code == 404, dropped.text

        survivor = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_bc}"
        )
        assert survivor.status_code == 200, survivor.text
        assert survivor.json()["status"] == "PENDING"
        assert survivor.json()["resource_ids"] == [merged_d, id_c]

        # Merge the surviving edge (now D+C) to finish the 3-way. A+C stays gone --
        # no stale candidate resurfaces.
        approve_bc = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_bc}/approve",
        )
        assert approve_bc.status_code == 200, approve_bc.text
        assert approve_bc.json()["merged_resource_id"] is not None

        still_dropped = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}"
        )
        assert still_dropped.status_code == 404, still_dropped.text

    @pytest.mark.anyio
    async def test_three_way_candidate_that_also_collides_is_dropped(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # Edge: a candidate that both dedupes an item (3-way A+B+C -> D+C) AND
        # collides with an earlier-rerouted candidate (A+C -> D+C). The 3-way is
        # processed second, so it both removes an orphan item and is deleted in the
        # same flush -- this must not error.
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ac = await _create_candidate(integration_client, [id_a, id_c])
        candidate_abc = await _create_candidate(integration_client, [id_a, id_b, id_c])
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
        )
        assert approve.status_code == 200, approve.text
        merged_d = approve.json()["merged_resource_id"]

        survivor = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ac}"
        )
        assert survivor.status_code == 200, survivor.text
        assert survivor.json()["resource_ids"] == [merged_d, id_c]

        dropped = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_abc}"
        )
        assert dropped.status_code == 404, dropped.text

    @pytest.mark.anyio
    async def test_subset_candidate_is_dropped_when_superset_is_approved(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # Approving the 3-way A+B+C -> D fully subsumes a pending A+B: it would
        # collapse to a single member [D], which can never be approved. It must be
        # deleted, not left as a PENDING dead end.
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])
        candidate_abc = await _create_candidate(integration_client, [id_a, id_b, id_c])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_abc}/approve",
        )
        assert approve.status_code == 200, approve.text

        dropped = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}"
        )
        assert dropped.status_code == 404, dropped.text

    @pytest.mark.anyio
    async def test_three_way_candidate_dedupes_merged_members(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        # A 3-way A+B+C where A+B is approved: A and B both collapse to D, so the
        # candidate must dedupe to D+C without tripping the
        # (merge_candidate_id, resource_id) unique constraint, and stay approvable.
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        id_c = await _create_resource(
            integration_client, og_create_res_fact, "Safaniya"
        )
        candidate_abc = await _create_candidate(integration_client, [id_a, id_b, id_c])
        candidate_ab = await _create_candidate(integration_client, [id_a, id_b])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_ab}/approve",
        )
        assert approve.status_code == 200, approve.text
        merged_d = approve.json()["merged_resource_id"]

        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_abc}"
        )
        assert resp.status_code == 200, resp.text
        # A and B collapsed to a single D member; C is preserved.
        assert resp.json()["status"] == "PENDING"
        assert resp.json()["resource_ids"] == [merged_d, id_c]

        approve_abc = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_abc}/approve",
        )
        assert approve_abc.status_code == 200, approve_abc.text
        assert approve_abc.json()["merged_resource_id"] is not None

    @pytest.mark.anyio
    async def test_composite_resource_matches_when_winners_agree(
        self,
        integration_client: AsyncClient,
        og_field_resource_factory,
        source_maker,
    ):
        # Resource A is "composite": two basin sources, RMI (winner) = "Foo" and
        # GEM = "Bar", so A resolves basin to "Foo".
        id_a = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [
                source_maker(source="rmi", managed=False, basin="Foo"),
                source_maker(source="gem", managed=False, basin="Bar"),
            ],
        )
        # Resource B has a single basin source = "Foo".
        id_b = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [source_maker(source="rmi", managed=False, basin="Foo")],
        )

        candidate_id = await _create_candidate(integration_client, [id_a, id_b])
        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        basin = next(c for c in body["compare"] if c["field"] == "basin")
        # Both resources resolve basin to "Foo" (A's RMI winner beats its GEM
        # "Bar"), so despite three sources in play the field matches.
        assert basin["status"] == "match"
        assert {
            (v["resource_id"], v["source"], v["value"]) for v in basin["values"]
        } == {
            (id_a, "rmi", "Foo"),
            (id_a, "gem", "Bar"),
            (id_b, "rmi", "Foo"),
        }


async def _create_disjoint_candidates(
    client: AsyncClient, fact: ResourceCreateFactory, count: int
) -> list[int]:
    """``count`` two-resource candidates sharing no resources, in creation order."""
    candidate_ids = []
    for i in range(count):
        id_a = await _create_resource(client, fact, f"Field {i}")
        id_b = await _create_resource(client, fact, f"Field {i} dup")
        candidate_ids.append(await _create_candidate(client, [id_a, id_b]))
    return candidate_ids


class TestMergeCandidateListIntegration:
    @pytest.mark.anyio
    async def test_pages_are_stable_when_candidates_share_a_timestamp(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ):
        candidate_ids = await _create_disjoint_candidates(
            integration_client, og_create_res_fact, 5
        )
        # Bulk creation can stamp many candidates with the same time; the id
        # tiebreak must still give every candidate exactly one page.
        async with integration_session_factory() as session:
            await session.execute(
                update(MergeCandidateModel).values(
                    created=datetime(2026, 1, 1, tzinfo=timezone.utc)
                )
            )
            await session.commit()

        seen = []
        for page in (1, 2, 3):
            resp = await integration_client.get(
                "/oil-gas-fields/merge-candidates",
                params={"page": page, "page_size": 2},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total_count"] == 5
            assert body["total_pages"] == 3
            seen.extend(item["id"] for item in body["items"])

        assert seen == sorted(candidate_ids, reverse=True)

    @pytest.mark.anyio
    async def test_status_filter_narrows_items_but_not_counts(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        approved_id, denied_id, pending_id = await _create_disjoint_candidates(
            integration_client, og_create_res_fact, 3
        )
        for candidate_id, action in ((approved_id, "approve"), (denied_id, "deny")):
            resp = await integration_client.post(
                f"/oil-gas-fields/merge-candidates/{candidate_id}/{action}"
            )
            assert resp.status_code == 200, resp.text

        pending = await integration_client.get(
            "/oil-gas-fields/merge-candidates", params={"status": "PENDING"}
        )
        assert pending.status_code == 200, pending.text
        assert [item["id"] for item in pending.json()["items"]] == [pending_id]
        assert pending.json()["total_count"] == 1
        assert pending.json()["status_counts"] == {
            "PENDING": 1,
            "APPROVED": 1,
            "DENIED": 1,
        }

        reviewed = await integration_client.get(
            "/oil-gas-fields/merge-candidates",
            params=[("status", "APPROVED"), ("status", "DENIED")],
        )
        assert {item["id"] for item in reviewed.json()["items"]} == {
            approved_id,
            denied_id,
        }

        unfiltered = await integration_client.get("/oil-gas-fields/merge-candidates")
        assert unfiltered.json()["total_count"] == 3

    @pytest.mark.anyio
    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    async def test_sort_by_reviewed_at_puts_unreviewed_last(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
        sort_order: str,
    ):
        first, second, unreviewed = await _create_disjoint_candidates(
            integration_client, og_create_res_fact, 3
        )
        for candidate_id in (first, second):
            resp = await integration_client.post(
                f"/oil-gas-fields/merge-candidates/{candidate_id}/deny"
            )
            assert resp.status_code == 200, resp.text

        resp = await integration_client.get(
            "/oil-gas-fields/merge-candidates",
            params={"sort_by": "reviewed_at", "sort_order": sort_order},
        )
        assert resp.status_code == 200, resp.text
        reviewed = [first, second] if sort_order == "asc" else [second, first]
        assert [item["id"] for item in resp.json()["items"]] == [
            *reviewed,
            unreviewed,
        ]

    @pytest.mark.anyio
    async def test_items_carry_display_names(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        candidate_id = await _create_candidate(integration_client, [id_a, id_b])

        resp = await integration_client.get("/oil-gas-fields/merge-candidates")
        assert resp.status_code == 200, resp.text
        (item,) = resp.json()["items"]
        # Same source on both resources: the tie goes to the first resource.
        assert item["name"] == "Ghawar"
        # Every status is counted, including ones with no candidates.
        assert resp.json()["status_counts"] == {
            "PENDING": 1,
            "APPROVED": 0,
            "DENIED": 0,
        }

        # The detail view names it the same way.
        detail = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert detail.json()["name"] == "Ghawar"

        # After approval the originals are emptied; the merged resource names it.
        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_id}/approve"
        )
        assert approve.status_code == 200, approve.text
        resp = await integration_client.get("/oil-gas-fields/merge-candidates")
        (item,) = resp.json()["items"]
        assert item["name"] == "Ghawar"
        detail = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert detail.json()["name"] == "Ghawar"

    @pytest.mark.anyio
    async def test_names_come_from_the_first_named_resource(
        self,
        integration_client: AsyncClient,
        og_field_resource_factory,
        source_maker,
    ):
        # Source rank doesn't matter: the first resource names the candidate,
        # though rmi outranks gem.
        id_gem = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [source_maker(source="gem", managed=False, name="From GEM")],
        )
        id_rmi = await _create_resource_with_sources(
            integration_client,
            og_field_resource_factory,
            [source_maker(source="rmi", managed=False, name="From RMI")],
        )
        candidate_id = await _create_candidate(integration_client, [id_gem, id_rmi])

        resp = await integration_client.get("/oil-gas-fields/merge-candidates")
        assert resp.status_code == 200, resp.text
        (item,) = resp.json()["items"]
        assert item["name"] == "From GEM"
        detail = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert detail.json()["name"] == "From GEM"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("sort_order", "expected"),
        [
            ("asc", ["Burgan", "Ghawar", "Zubair"]),
            ("desc", ["Zubair", "Ghawar", "Burgan"]),
        ],
    )
    async def test_sorts_by_name_across_pages(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
        sort_order: str,
        expected: list[str],
    ):
        # Created out of name order, so a created-order result can't pass.
        for name in ["Ghawar", "Zubair", "Burgan"]:
            first = await _create_resource(integration_client, og_create_res_fact, name)
            second = await _create_resource(
                integration_client, og_create_res_fact, f"{name} twin"
            )
            await _create_candidate(integration_client, [first, second])

        names = []
        for page in (1, 2):
            resp = await integration_client.get(
                "/oil-gas-fields/merge-candidates",
                params={
                    "sort_by": "name",
                    "sort_order": sort_order,
                    "page": page,
                    "page_size": 2,
                },
            )
            assert resp.status_code == 200, resp.text
            names.extend(item["name"] for item in resp.json()["items"])

        assert names == expected

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("sort_order", "expected"),
        [
            # Work still to do first; newest first within each status.
            ("asc", ["newer pending", "older pending", "denied", "approved"]),
            ("desc", ["approved", "denied", "newer pending", "older pending"]),
        ],
    )
    async def test_sorts_by_status(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
        sort_order: str,
        expected: list[str],
    ):
        ids = {}
        # Created oldest first, so creation order alone can't pass.
        for label in ["approved", "older pending", "denied", "newer pending"]:
            first = await _create_resource(
                integration_client, og_create_res_fact, label
            )
            second = await _create_resource(
                integration_client, og_create_res_fact, f"{label} twin"
            )
            ids[label] = await _create_candidate(integration_client, [first, second])
        for label, action in [("approved", "approve"), ("denied", "deny")]:
            resp = await integration_client.post(
                f"/oil-gas-fields/merge-candidates/{ids[label]}/{action}"
            )
            assert resp.status_code == 200, resp.text

        resp = await integration_client.get(
            "/oil-gas-fields/merge-candidates",
            params={"sort_by": "status", "sort_order": sort_order},
        )
        assert resp.status_code == 200, resp.text
        label_by_id = {candidate_id: label for label, candidate_id in ids.items()}
        assert [label_by_id[item["id"]] for item in resp.json()["items"]] == expected

    @pytest.mark.anyio
    async def test_refuses_callers_the_read_model_cannot_serve(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        """Names come from the field list's precomputed rows, which exist only
        for exact permission profiles, so the queue refuses the same callers
        the field list does."""
        id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
        id_b = await _create_resource(integration_client, og_create_res_fact, "Burgan")
        candidate_id = await _create_candidate(integration_client, [id_a, id_b])

        # Missing every public source but gem.
        app.dependency_overrides[get_token_claims] = lambda: TokenClaims(
            sub="test|user-1",
            permissions=frozenset({SOURCE_READ_GEM, MERGE_CANDIDATE_READ}),
        )
        for path in [
            "/oil-gas-fields/merge-candidates",
            f"/oil-gas-fields/merge-candidates/{candidate_id}",
        ]:
            resp = await integration_client.get(path)
            assert resp.status_code == 403, resp.text
            assert "missing read access to public source" in resp.json()["detail"]

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "params",
        [
            {"status": "MAYBE"},
            {"sort_by": "size"},
            {"sort_order": "sideways"},
            {"page": 0},
            {"page_size": 201},
        ],
    )
    async def test_rejects_invalid_params(
        self, integration_client: AsyncClient, params: dict
    ):
        resp = await integration_client.get(
            "/oil-gas-fields/merge-candidates", params=params
        )
        assert resp.status_code == 422, resp.text


class TestMergeCandidateSearchIntegration:
    """``q`` on the list: a candidate matches when any of its resources (or its
    merged resource) matches the resource list's search, or a numeric ``q``
    names one of those resources."""

    @pytest.fixture
    def make_resource(
        self, integration_client, og_field_resource_factory, source_maker
    ):
        # The searchable fields default to blank, so only what a test sets can
        # match (the factory would otherwise fill them with random text).
        async def _make(*, source: str = "rmi", **fields) -> int:
            searchable = {
                "name_local": None,
                "basin": None,
                "state_province": None,
                "region": None,
            }
            return await _create_resource_with_sources(
                integration_client,
                og_field_resource_factory,
                [
                    source_maker(
                        source=source, managed=False, **{**searchable, **fields}
                    )
                ],
            )

        return _make

    async def _search(self, client: AsyncClient, **params) -> list[int]:
        resp = await client.get("/oil-gas-fields/merge-candidates", params=params)
        assert resp.status_code == 200, resp.text
        return [item["id"] for item in resp.json()["items"]]

    @pytest.mark.anyio
    async def test_matches_either_resource_by_name(
        self, integration_client: AsyncClient, make_resource
    ):
        first = await make_resource(name="Zubair Main")
        second = await make_resource(name="Zubayr Main")
        candidate_id = await _create_candidate(integration_client, [first, second])
        other = await _create_candidate(
            integration_client,
            [await make_resource(name="Ghawar"), await make_resource(name="Ghawar")],
        )

        # Case-insensitive substring, matching only the second resource.
        assert await self._search(integration_client, q="zubayr") == [candidate_id]
        assert await self._search(integration_client, q="Zub") == [candidate_id]
        assert other not in await self._search(integration_client, q="zub")

    @pytest.mark.anyio
    async def test_matches_the_other_search_fields(
        self, integration_client: AsyncClient, make_resource
    ):
        candidate_id = await _create_candidate(
            integration_client,
            [
                await make_resource(name="Alpha", basin="Qwertian Basin"),
                await make_resource(name="Alpha", region="Middle East"),
            ],
        )

        assert await self._search(integration_client, q="qwertian") == [candidate_id]

    @pytest.mark.anyio
    async def test_finds_an_approved_candidate_by_its_merged_resource(
        self, integration_client: AsyncClient, make_resource
    ):
        original = await make_resource(name="Safaniya")
        candidate_id = await _create_candidate(
            integration_client,
            [original, await make_resource(name="Safaniya")],
        )
        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_id}/approve"
        )
        assert approve.status_code == 200, approve.text

        # The originals are emptied by the merge; only the merged resource
        # still carries the name.
        assert await self._search(integration_client, q="safaniya") == [candidate_id]
        # By id, a merged-away original still finds the candidate that merged it.
        assert await self._search(integration_client, q=str(original)) == [candidate_id]

    @pytest.mark.anyio
    async def test_numeric_q_matches_resource_ids(
        self, integration_client: AsyncClient, make_resource
    ):
        target = await make_resource(name="Unrelated")
        by_id = await _create_candidate(
            integration_client, [target, await make_resource(name="Unrelated")]
        )
        await _create_candidate(
            integration_client,
            [await make_resource(name="Ghawar"), await make_resource(name="Ghawar")],
        )

        assert await self._search(integration_client, q=str(target)) == [by_id]
        # Candidate ids are not searched: no resource has this id.
        assert await self._search(integration_client, q="987654321") == []
        # Too long to be an id; still searched as text, without erroring.
        assert await self._search(integration_client, q="9" * 30) == []
        # Past Python's int-conversion limit (4300 digits).
        assert await self._search(integration_client, q="9" * 5000) == []
        # Non-ASCII digits are text, not ids.
        assert await self._search(integration_client, q="²") == []

    @pytest.mark.anyio
    async def test_numeric_q_also_matches_digits_in_text(
        self, integration_client: AsyncClient, make_resource
    ):
        by_text = await _create_candidate(
            integration_client,
            [
                await make_resource(name="Block 990077"),
                await make_resource(name="Block 990077"),
            ],
        )

        # Far above any resource id here, so only the name can match.
        assert await self._search(integration_client, q="990077") == [by_text]

    @pytest.mark.anyio
    async def test_combines_with_status_and_leaves_counts_whole_queue(
        self, integration_client: AsyncClient, make_resource
    ):
        pending = await _create_candidate(
            integration_client,
            [await make_resource(name="Rumaila"), await make_resource(name="Rumaila")],
        )
        denied = await _create_candidate(
            integration_client,
            [await make_resource(name="Rumaila"), await make_resource(name="Rumaila")],
        )
        await _create_candidate(
            integration_client,
            [await make_resource(name="Ghawar"), await make_resource(name="Ghawar")],
        )
        resp = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{denied}/deny"
        )
        assert resp.status_code == 200, resp.text

        resp = await integration_client.get(
            "/oil-gas-fields/merge-candidates",
            params={"q": "rumaila", "status": "PENDING"},
        )
        body = resp.json()
        assert [item["id"] for item in body["items"]] == [pending]
        assert body["total_count"] == 1
        assert body["status_counts"] == {"PENDING": 2, "APPROVED": 0, "DENIED": 1}

    @pytest.mark.anyio
    async def test_blank_q_is_no_search(
        self, integration_client: AsyncClient, make_resource
    ):
        candidate_id = await _create_candidate(
            integration_client,
            [await make_resource(name="Ghawar"), await make_resource(name="Ghawar")],
        )

        assert await self._search(integration_client, q="   ") == [candidate_id]

    @pytest.mark.anyio
    async def test_ignores_names_from_unlicensed_sources(
        self, integration_client: AsyncClient, make_resource
    ):
        candidate_id = await _create_candidate(
            integration_client,
            [
                await make_resource(source="wm", name="Wmonly Field"),
                await make_resource(source="wm", name="Wmonly Field"),
            ],
        )
        # With every source, the name matches, so only licensing hides it below.
        assert await self._search(integration_client, q="wmonly") == [candidate_id]

        # Public sources only: the read model serves this profile, without wm.
        app.dependency_overrides[get_token_claims] = lambda: TokenClaims(
            sub="test|public-only",
            permissions=frozenset(
                {RESOURCE_READ, MERGE_CANDIDATE_READ}
                | {f"{SOURCE_READ_PREFIX}{source}" for source in PUBLIC_SOURCES}
            ),
        )

        assert await self._search(integration_client, q="wmonly") == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("prior_candidates", "apply_merges", "expected_created", "expected_skipped"),
    [
        ((), False, 0, 0),
        ((), True, 2, 0),
        ((0,), True, 1, 1),
        ((0,), False, 0, 1),
        ((0, 1), True, 0, 2),
        ((2,), True, 2, 0),
    ],
    ids=[
        "dry-run-writes-nothing",
        "real-run-creates-one-per-group",
        "real-run-skips-the-group-that-already-has-a-candidate",
        "dry-run-skips-match-the-real-run",
        "repeat-real-run-creates-nothing",
        "a-candidate-outside-the-matched-groups-is-ignored",
    ],
)
async def test_link_all_counts_and_writes(
    integration_client: AsyncClient,
    og_create_res_fact: ResourceCreateFactory,
    prior_candidates: tuple[int, ...],
    apply_merges: bool,
    expected_created: int,
    expected_skipped: int,
):
    ids = [
        await _create_resource(integration_client, og_create_res_fact, f"Field {n}")
        for n in range(6)
    ]
    pairs = [(ids[0], ids[1]), (ids[2], ids[3]), (ids[4], ids[5])]
    groups = pairs[:2]
    for index in prior_candidates:
        await _create_candidate(integration_client, list(pairs[index]))

    with patch.object(link_actions, "match", autospec=True) as match:
        match.return_value = groups
        resp = await integration_client.post(
            "/oil-gas-fields/merge-candidates/link-all",
            params={"apply_merges": apply_merges},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "apply_merges": apply_merges,
        "match_groups": [list(group) for group in groups],
        "merge_candidates_created": expected_created,
        "merge_candidates_skipped": expected_skipped,
    }

    expected_persisted = {frozenset(pairs[i]) for i in prior_candidates}
    if apply_merges:
        expected_persisted |= {frozenset(group) for group in groups}

    listed = await integration_client.get("/oil-gas-fields/merge-candidates")
    assert listed.status_code == 200, listed.text
    assert {
        frozenset(candidate["resource_ids"]) for candidate in listed.json()["items"]
    } == expected_persisted


@pytest.mark.anyio
async def test_link_all_reports_a_failed_commit_instead_of_success(
    integration_client: AsyncClient,
    og_create_res_fact: ResourceCreateFactory,
):
    """A commit that fails must not surface as a 200 describing writes that rolled back."""
    id_a = await _create_resource(integration_client, og_create_res_fact, "Ghawar")
    id_b = await _create_resource(integration_client, og_create_res_fact, "Ghawar")

    async def failing_commit(self):
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    with (
        patch.object(link_actions, "match", autospec=True) as match,
        patch.object(UnitOfWork, "commit", failing_commit),
    ):
        match.return_value = [(id_a, id_b)]
        resp = await integration_client.post(
            "/oil-gas-fields/merge-candidates/link-all?apply_merges=true"
        )

    assert resp.status_code == 503, resp.text
    assert resp.json() == {"detail": "Database unavailable."}

    listed = await integration_client.get("/oil-gas-fields/merge-candidates")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []


@pytest.mark.anyio
async def test_link_all_matches_only_the_callers_licensed_sources(
    integration_client: AsyncClient,
):
    app.dependency_overrides[get_token_claims] = lambda: TokenClaims(
        sub="test|user-1",
        permissions=frozenset({SOURCE_READ_GEM, MERGE_CANDIDATE_CREATE}),
    )

    with patch.object(link_actions, "match", autospec=True) as match:
        match.return_value = []
        resp = await integration_client.post(
            "/oil-gas-fields/merge-candidates/link-all"
        )

    assert resp.status_code == 200, resp.text
    assert match.call_args.kwargs["licensed_sources"] == frozenset({"gem"})
