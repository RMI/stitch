"""End-to-end coverage that the wrapped DB action call sites emit the expected
``query_name`` labels.

The unit tests in ``test_query_timing.py`` exercise ``named_query`` around raw
statements; these drive the real endpoints and action functions through the
router / action / engine path so a typo in a label or a misplaced scope is
caught. Query timing is registered on the integration engine with
``log_all_queries=True`` and the sink is captured, so every statement a request
runs is inspected.

Assertions compare the *exact* set of labels an operation emits (not just a
subset), so a secondary statement that carries an unexpected label -- or a scope
that leaks onto the wrong query -- fails the test. Unlabeled statements
(connection setup, transaction control, ORM-internal reads that legitimately run
outside any ``named_query`` scope) are excluded: the label is optional by design,
and asserting their absence would just pin SQLite/driver noise.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import merge_candidate_actions as mca
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.model import MembershipModel, MembershipStatus, ResourceModel
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.db.priorities import seed_or_refresh_defaults
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


def _labels(events: list[dict]) -> set[str]:
    """The set of query_name labels present among captured events."""
    return {event["query_name"] for event in events if "query_name" in event}


def _assert_labels(events: list[dict], expected: set[str]) -> None:
    """Assert the labeled events are *exactly* ``expected`` (no missing/extra labels)."""
    actual = _labels(events)
    assert actual == expected, f"unexpected labels: {actual ^ expected}"


class TestEndpointQueryLabels:
    """Drive the real HTTP read endpoints and assert the exact labels each emits."""

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

        _assert_labels(
            captured_query_events,
            {"resources.count", "resources.list_ids", "resources.list_hydrate"},
        )

    @pytest.mark.anyio
    async def test_filter_options_endpoint_labels(
        self,
        integration_client: AsyncClient,
        captured_query_events: list[dict],
    ):
        # filter-options returns every filterable field in one combined query.
        response = await integration_client.get("/oil-gas-fields/filter-options")
        assert response.status_code == 200, response.text

        _assert_labels(captured_query_events, {"resources.filter_options"})

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

        # get_resolved -> resolve_root_id then get; both statements labeled.
        _assert_labels(
            captured_query_events, {"resources.resolve_root", "resources.detail"}
        )


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
    # Direct seeding bypasses the action layer; seed the default priority rows the
    # coalescing path requires (done before any captured_query_events.clear()).
    await seed_or_refresh_defaults(session, user, resource_id)
    return model.id


class TestActionCallSiteLabels:
    """Call the DB action functions directly and assert the exact labels each emits.

    Each operation is captured on its own (clear -> call -> assert exact set) so
    the fan-out of every action -- including nested labeled helpers -- is pinned,
    covering the write paths, sources.*, merge_candidates.*, and every
    third-level sub-label that the endpoint tests above do not reach.
    """

    @pytest.mark.anyio
    async def test_resource_read_labels(
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
        _assert_labels(
            captured_query_events,
            {"resources.count", "resources.list_ids", "resources.list_hydrate"},
        )

        captured_query_events.clear()
        await resource_actions.filter_options(session)
        _assert_labels(captured_query_events, {"resources.filter_options"})

        captured_query_events.clear()
        await resource_actions.get_resolved(session, created.id)
        _assert_labels(
            captured_query_events, {"resources.resolve_root", "resources.detail"}
        )

        captured_query_events.clear()
        await resource_actions.field_source_values(
            session, created.id, next(iter(ATTRIBUTE_NAMES))
        )
        _assert_labels(
            captured_query_events,
            {"resources.resolve_root", "resources.field_source_values"},
        )

    @pytest.mark.anyio
    async def test_create_label(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session

        captured_query_events.clear()
        await resource_actions.create(
            session, test_user, og_create_res_fact(name="Created")
        )
        # create() with source_data fans out to the source helpers.
        _assert_labels(
            captured_query_events,
            {"resources.create", "sources.get_or_create", "sources.attach"},
        )

    @pytest.mark.anyio
    async def test_merge_labels(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
        captured_query_events: list[dict],
    ):
        session = seeded_integration_session
        first = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Merge A")
        )
        second = await resource_actions.create(
            session, test_user, og_create_res_fact(name="Merge B")
        )
        await session.commit()

        captured_query_events.clear()
        await resource_actions.apply_resource_merge(
            session, test_user, [first.id, second.id]
        )
        _assert_labels(
            captured_query_events, {"resources.merge.load", "resources.merge.apply"}
        )

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
        await _attach_source(session, test_user, rid, "gem", country="SAU")
        await _attach_source(session, test_user, rid, "rmi", country="USA")
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

        # The action re-prioritizes, then returns field_source_values(), which
        # itself resolves the root and re-reads the candidates.
        _assert_labels(
            captured_query_events,
            {
                "resources.set_field_source_priority.load",
                "resources.set_field_source_priority.candidates",
                "resources.set_field_source_priority.persist",
                "resources.resolve_root",
                "resources.field_source_values",
            },
        )

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
        _assert_labels(captured_query_events, {"sources.create"})

        captured_query_events.clear()
        await source_actions.create_and_attach_sources(
            session, test_user, [source_maker(managed=False, source="rmi")], parent.id
        )
        _assert_labels(captured_query_events, {"sources.create_and_attach"})

        captured_query_events.clear()
        await source_actions.get_or_create_sources(
            session, test_user, [source_maker(managed=False, source="wm")]
        )
        _assert_labels(captured_query_events, {"sources.get_or_create"})

        captured_query_events.clear()
        await source_actions.attach_sources_to_resource(
            session, parent.id, [source_maker(managed=False, source="bc")], test_user
        )
        _assert_labels(captured_query_events, {"sources.attach"})

        captured_query_events.clear()
        await source_actions.get_source(session, created.id)
        _assert_labels(captured_query_events, {"sources.detail"})

        captured_query_events.clear()
        await source_actions.get_sources(session, [created.id])
        _assert_labels(captured_query_events, {"sources.get_by_ids"})

        captured_query_events.clear()
        await source_actions.query(session, OGFieldQueryParams())
        _assert_labels(
            captured_query_events,
            {"sources.count", "sources.list_ids", "sources.list_hydrate"},
        )

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
        _assert_labels(
            captured_query_events,
            {
                "merge_candidates.create.load_resources",
                "merge_candidates.create.check_existing",
                "merge_candidates.create.persist",
            },
        )

        captured_query_events.clear()
        await mca.list_merge_candidates(session)
        _assert_labels(captured_query_events, {"merge_candidates.list"})

        captured_query_events.clear()
        await mca.get_merge_candidate(session, approved.id)
        _assert_labels(
            captured_query_events,
            {
                "merge_candidates.detail.load",
                "merge_candidates.detail.coalesce",
            },
        )

        captured_query_events.clear()
        await mca.approve_merge_candidate(
            session,
            test_user,
            approved.id,
            MergeCandidateReviewRequest(review_notes="ok"),
        )
        # approve delegates the actual merge to apply_resource_merge.
        _assert_labels(
            captured_query_events,
            {
                "merge_candidates.approve.load",
                "merge_candidates.approve.load_resources",
                "merge_candidates.approve.persist",
                "resources.merge.load",
                "resources.merge.apply",
            },
        )

        captured_query_events.clear()
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
        _assert_labels(
            captured_query_events,
            {
                "merge_candidates.create.load_resources",
                "merge_candidates.create.check_existing",
                "merge_candidates.create.persist",
                "merge_candidates.deny.load",
                "merge_candidates.deny.persist",
            },
        )
