"""Integration tests for the merge-candidate detail endpoint (real SQLite)."""

from collections.abc import Sequence

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import ResourceCreateFactory
from stitch.api.db.model import OGFieldResourceSourcePriority
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
    async def test_detail_includes_resources_and_compare(
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
        # resource_ids preserved alongside the richer `resources`
        assert body["resource_ids"] == [id_a, id_b]

        # `resources`: one full detail object per candidate resource, in order
        assert [r["id"] for r in body["resources"]] == [id_a, id_b]
        for resource in body["resources"]:
            assert {"id", "data", "provenance", "source_data"} <= set(resource)

        # `compare`: one entry per OilGasFieldBase field, values per contributing
        # source (winner-first), reusing the OGFieldSourceValueView shape.
        compare = {c["field"]: c for c in body["compare"]}
        name_cmp = compare["name"]
        for entry in name_cmp["values"]:
            assert {"source", "id", "value", "priority"} <= set(entry)

        # RMI (highest priority) carries the given names on both resources; the
        # baseline resources[0]=A wins the RMI tie by id, so A's name stays put
        # while B's differing name is present at lower precedence -> unchanged.
        assert name_cmp["status"] == "unchanged"
        assert name_cmp["values"][0]["value"] == "Ghawar"  # merged winner
        rmi_names = {v["value"] for v in name_cmp["values"] if v["source"] == "rmi"}
        assert {"Ghawar", "Burgan"} <= rmi_names

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
        # Live compute: originals are repointed with memberships INACTIVE, so
        # their coalesced data is a null-shell with no surviving sources.
        # (Freeze snapshot is deferred.)
        for resource in body["resources"]:
            assert resource["data"]["name"] is None
        for entry in body["compare"]:
            assert entry["status"] == "unchanged"
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

        # Override A's ordering so GEM outranks RMI -> A's coalesced name flips.
        async with integration_session_factory() as session:
            session.add(
                OGFieldResourceSourcePriority(
                    resource_id=id_a, source="gem", priority=0
                )
            )
            await session.commit()

        detail_a = await integration_client.get(f"/oil-gas-fields/{id_a}/detail")
        assert detail_a.status_code == 200, detail_a.text
        assert detail_a.json()["data"]["name"] == "GEM-name"  # override in effect

        candidate_id = await _create_candidate(integration_client, [id_a, id_b])
        resp = await integration_client.get(
            f"/oil-gas-fields/merge-candidates/{candidate_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Baseline (resources[0] = A) reflects the override...
        assert body["resources"][0]["data"]["name"] == "GEM-name"
        # ...but the merge resets to default order (RMI wins), so the field
        # changes -> mismatch, with RMI as the merged winner.
        name_cmp = next(c for c in body["compare"] if c["field"] == "name")
        assert name_cmp["status"] == "mismatch"
        assert name_cmp["values"][0]["value"] == "RMI-name"

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
