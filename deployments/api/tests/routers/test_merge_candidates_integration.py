"""Integration tests for the merge-candidate detail endpoint (real SQLite)."""

from httpx import AsyncClient
import pytest

from tests.factories import ResourceCreateFactory


async def _create_resource(
    client: AsyncClient, fact: ResourceCreateFactory, name: str
) -> int:
    payload = fact(name=name).model_dump(mode="json")
    resp = await client.post("/oil-gas-fields/", json=payload)
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

        # `compare`: one entry per OilGasFieldBase field; `name` differs across
        # the two resources (RMI is highest priority and carries the given name)
        compare = {c["field"]: c for c in body["compare"]}
        name_cmp = compare["name"]
        assert name_cmp["status"] == "mismatch"
        assert {v["resource_id"]: v["value"] for v in name_cmp["values"]} == {
            id_a: "Ghawar",
            id_b: "Burgan",
        }

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
        # their coalesced data is a null-shell. (Freeze snapshot is deferred.)
        for resource in body["resources"]:
            assert resource["data"]["name"] is None
