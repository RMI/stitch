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


class TestStaleCandidateResolution:
    """STIT-418 AC 3: approving an overlapping merge makes a pending candidate stale.

    candidate1 {A,B} and candidate2 {B,D} both pending; approving candidate1
    repoints B, so candidate2 now overlaps an already-merged resource.
    """

    @pytest.mark.anyio
    async def test_overlapping_approval_surfaces_the_move_and_blocks_reapprove(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        id_a = await _create_resource(integration_client, og_create_res_fact, "A")
        id_b = await _create_resource(integration_client, og_create_res_fact, "B")
        id_d = await _create_resource(integration_client, og_create_res_fact, "D")

        cand1 = await _create_candidate(integration_client, [id_a, id_b])
        cand2 = await _create_candidate(integration_client, [id_b, id_d])

        approve = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{cand1}/approve",
            json={"review_notes": "ok"},
        )
        assert approve.status_code == 200, approve.text
        merged_id = approve.json()["merged_resource_id"]
        assert merged_id is not None

        expected_move = [{"resource_id": id_b, "repointed_to": merged_id}]

        # candidate2 detail reports B -> merged_id (only the member that moved).
        detail = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{cand2}"
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["repointed_resources"] == expected_move

        queue = await integration_client.get("/oil-gas-fields/merge-candidates")
        assert queue.status_code == 200, queue.text
        rows = {c["id"]: c for c in queue.json()}
        # The queue row carries the same signal...
        assert rows[cand2]["repointed_resources"] == expected_move
        # ...and the APPROVED candidate reports no staleness (PENDING-only rule).
        assert rows[cand1]["repointed_resources"] == []

        # Approving candidate2 now fails with an id-naming message, not a repr()
        # memory address (the STIT-418 bug), and leaves it untouched.
        reapprove = await integration_client.post(
            f"/oil-gas-fields/merge-candidates/{cand2}/approve",
        )
        assert reapprove.status_code == 400, reapprove.text
        message = reapprove.json()["detail"]
        assert str(id_b) in message
        assert str(merged_id) in message
        assert "object at 0x" not in message

        after = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{cand2}"
        )
        assert after.json()["status"] == "PENDING"
