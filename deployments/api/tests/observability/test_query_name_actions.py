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
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import merge_candidate_actions as mca
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.model import MembershipModel, MembershipStatus, ResourceModel
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.entities import (
    MergeCandidateCreateRequest,
    MergeCandidateReviewRequest,
    OGFieldQueryParams,
    User,
)
from stitch.api.observability import query_timing
from tests.utils import make_source_model


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
        # filter-options returns every filterable field in one query.
        response = await integration_client.get("/oil-gas-fields/filter-options")
        assert response.status_code == 200, response.text

        assert "resources.filter_options" in _query_names(captured_query_events)

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


async def _attach_source(
    session: AsyncSession, user: User, resource_id: int, source: str, **values
) -> int:
    """Attach one active source (carrying ``values``) to a resource; return its pk."""
    model = make_source_model(source=source, created_by_id=user.id, **values)
    session.add(model)
    await session.flush()
    session.add(
        MembershipModel.create(
            created_by=user,
            resource_id=resource_id,
            source=model.source,
            source_pk=model.id,
            status=MembershipStatus.ACTIVE,
        )
    )
    await session.flush()
    return model.id


class TestActionCallSiteLabels:
    """Drive the DB action functions directly and assert the exact labels they emit.

    The endpoint tests above cover the read paths; these cover the remaining
    call sites (write paths, sources, merge candidates, and every third-level
    sub-label) so a typo'd or misplaced ``named_query`` string fails a test
    instead of shipping a mislabeled event.
    """

    @pytest.mark.anyio
    async def test_resource_action_labels(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session
        created = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Labelled")
        )
        await session.commit()

        captured_query_events.clear()
        await resource_actions.query(session, OGFieldQueryParams())
        await resource_actions.filter_options(session)
        await resource_actions.get_resolved(session, created.id)
        await resource_actions.field_source_values(
            session, created.id, next(iter(ATTRIBUTE_NAMES))
        )

        assert {
            "resources.count",
            "resources.list_ids",
            "resources.list_hydrate",
            "resources.filter_options",
            "resources.resolve_root",
            "resources.detail",
            "resources.field_source_values",
        } <= _query_names(captured_query_events)

    @pytest.mark.anyio
    async def test_create_and_merge_labels(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session

        captured_query_events.clear()
        first = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Merge A")
        )
        second = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Merge B")
        )
        # create (with source_data) fans out to the source helpers too.
        assert {
            "resources.create",
            "sources.get_or_create",
            "sources.attach",
        } <= _query_names(captured_query_events)

        captured_query_events.clear()
        await resource_actions.apply_resource_merge(
            session, test_user, [first.id, second.id]
        )
        assert {
            "resources.merge.load",
            "resources.merge.apply",
        } <= _query_names(captured_query_events)

    @pytest.mark.anyio
    async def test_set_field_source_priority_labels(
        self,
        seeded_integration_session: AsyncSession,
        integration_session_factory,
        test_user: User,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session
        resource = ResourceModel.create(created_by=test_user)
        session.add(resource)
        await session.flush()
        rid = resource.id
        await _attach_source(session, test_user, rid, "gem", country="Gemland")
        await _attach_source(session, test_user, rid, "rmi", country="Rmiland")
        await session.commit()

        # Both sources carry `country`, so both are eligible; reverse the current
        # winner-first order to force an actual re-prioritization (the persist path).
        current = await resource_actions.field_source_values(session, rid, "country")
        reordered = [view.source_id for view in reversed(current)]
        assert len(reordered) == 2

        # Run in a fresh session (one per request in prod) so the `.load` get()
        # issues SQL rather than hitting this session's identity map.
        captured_query_events.clear()
        async with integration_session_factory() as fresh:
            await resource_actions.set_field_source_priority(
                fresh, test_user, rid, "country", reordered
            )
            await fresh.commit()

        assert {
            "resources.set_field_source_priority.load",
            "resources.set_field_source_priority.candidates",
            "resources.set_field_source_priority.persist",
        } <= _query_names(captured_query_events)

    @pytest.mark.anyio
    async def test_source_action_labels(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        source_maker,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session
        parent = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Parent")
        )
        await session.commit()

        captured_query_events.clear()
        created = await source_actions.create_source(
            session, test_user, source_maker(managed=False, source="gem")
        )
        await source_actions.create_and_attach_sources(
            session, test_user, [source_maker(managed=False, source="rmi")], parent.id
        )
        await source_actions.get_or_create_sources(
            session, test_user, [source_maker(managed=False, source="wm")]
        )
        await source_actions.attach_sources_to_resource(
            session, parent.id, [source_maker(managed=False, source="bc")], test_user
        )
        await source_actions.get_source(session, created.id)
        await source_actions.get_sources(session, [created.id])
        await source_actions.query(session, OGFieldQueryParams())

        assert {
            "sources.create",
            "sources.create_and_attach",
            "sources.get_or_create",
            "sources.attach",
            "sources.detail",
            "sources.get_by_ids",
            "sources.count",
            "sources.list_ids",
            "sources.list_hydrate",
        } <= _query_names(captured_query_events)

    @pytest.mark.anyio
    async def test_merge_candidate_action_labels(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session
        resources = [
            await resource_actions.create(
                session, test_user, og_create_res_fact(name=f"Cand {i}")
            )
            for i in range(4)
        ]
        await session.commit()

        captured_query_events.clear()
        approved = await mca.create_merge_candidate(
            session,
            test_user,
            MergeCandidateCreateRequest(
                resource_ids=[resources[0].id, resources[1].id]
            ),
        )
        await mca.list_merge_candidates(session)
        await mca.get_merge_candidate(session, approved.id)
        await mca.approve_merge_candidate(
            session,
            test_user,
            approved.id,
            MergeCandidateReviewRequest(review_notes="ok"),
        )

        denied = await mca.create_merge_candidate(
            session,
            test_user,
            MergeCandidateCreateRequest(
                resource_ids=[resources[2].id, resources[3].id]
            ),
        )
        await mca.deny_merge_candidate(
            session,
            test_user,
            denied.id,
            MergeCandidateReviewRequest(review_notes="no"),
        )

        assert {
            "merge_candidates.create.load_resources",
            "merge_candidates.create.check_existing",
            "merge_candidates.create.persist",
            "merge_candidates.list",
            "merge_candidates.detail.load",
            "merge_candidates.detail.coalesce",
            "merge_candidates.detail.default_priority",
            "merge_candidates.approve.load",
            "merge_candidates.approve.load_resources",
            "merge_candidates.approve.persist",
            "merge_candidates.deny.load",
            "merge_candidates.deny.persist",
            # approve delegates to apply_resource_merge
            "resources.merge.load",
            "resources.merge.apply",
        } <= _query_names(captured_query_events)
