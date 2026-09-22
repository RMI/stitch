"""End-to-end coverage that the wrapped DB action call sites emit the expected
``query_name`` labels.

The unit tests in ``test_query_timing.py`` exercise ``named_query`` around raw
statements; these drive the real endpoints through the router → action → engine
path so a typo in a label (e.g. ``resources.count``) or a misplaced scope is
caught. Query timing is registered on the integration engine with
``log_all_queries=True`` and the sink is captured, so every statement a request
runs is inspected.
"""

import pytest
from httpx import AsyncClient

from stitch.api.observability import query_timing


@pytest.fixture
def captured_query_events(integration_engine, monkeypatch) -> list[dict]:
    """Capture every query event emitted while hitting the integration engine."""
    events: list[dict] = []
    monkeypatch.setattr(
        query_timing, "emit_query_event", lambda event: events.append(event)
    )
    query_timing.register_query_timing(
        integration_engine.sync_engine, slow_query_ms=0, log_all_queries=True
    )
    return events


def _query_names(events: list[dict]) -> set[str]:
    return {event["query_name"] for event in events if "query_name" in event}


class TestActionQueryLabels:
    @pytest.mark.anyio
    async def test_list_endpoint_labels(
        self,
        integration_client: AsyncClient,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        # A row must exist for the hydrate query to run (skipped when empty).
        create = await integration_client.post(
            "/oil-gas-fields/",
            json=og_create_res_fact(name="Labeled Resource").model_dump(mode="json"),
        )
        assert create.status_code == 200, create.text

        captured_query_events.clear()
        response = await integration_client.get("/oil-gas-fields/")
        assert response.status_code == 200, response.text

        names = _query_names(captured_query_events)
        assert {
            "resources.count",
            "resources.list_ids",
            "resources.list_hydrate",
        } <= names

    @pytest.mark.anyio
    async def test_filter_options_endpoint_labels(
        self,
        integration_client: AsyncClient,
        captured_query_events: list[dict],
    ):
        response = await integration_client.get(
            "/oil-gas-fields/filter-options", params={"field": "country"}
        )
        assert response.status_code == 200, response.text

        assert "filter_options.country" in _query_names(captured_query_events)

    @pytest.mark.anyio
    async def test_detail_endpoint_labels(
        self,
        integration_client: AsyncClient,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        create = await integration_client.post(
            "/oil-gas-fields/",
            json=og_create_res_fact(name="Detail Resource").model_dump(mode="json"),
        )
        assert create.status_code == 200, create.text
        created_id = create.json()["id"]

        captured_query_events.clear()
        response = await integration_client.get(f"/oil-gas-fields/{created_id}")
        assert response.status_code == 200, response.text

        # get_resolved -> resolve_root_id (resources.resolve_root) then get
        # (resources.detail); assert both, so the secondary statement is covered.
        names = _query_names(captured_query_events)
        assert {"resources.resolve_root", "resources.detail"} <= names
