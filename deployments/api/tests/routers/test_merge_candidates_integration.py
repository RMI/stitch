"""Integration tests for the merge-candidate detail endpoint (real SQLite)."""

from collections.abc import Sequence

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import ResourceCreateFactory
from stitch.api.db.model import MembershipModel, OGFieldResourceSourcePriority
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
