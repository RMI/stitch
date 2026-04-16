from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stitch.api.db import merge_candidate_actions as mca
from stitch.api.db.errors import ResourceIntegrityError, ResourceNotFoundError


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


@pytest.mark.anyio
async def test_preview_merge_candidate_returns_coalesced_view(monkeypatch):
    session = AsyncMock()

    candidate = SimpleNamespace(
        id=1,
        items=[
            SimpleNamespace(resource_id=19, position=1),
            SimpleNamespace(resource_id=18, position=0),
        ],
    )

    source_model_1 = SimpleNamespace(as_entity=lambda: SimpleNamespace(name="A"))
    source_model_2 = SimpleNamespace(as_entity=lambda: SimpleNamespace(name="B"))

    async def fake_load_candidate_model(session_arg, candidate_id):
        assert session_arg is session
        assert candidate_id == 1
        return candidate

    async def fake_load_mergeable_resources(session_arg, resource_ids):
        assert session_arg is session
        assert resource_ids == [18, 19]
        return [
            SimpleNamespace(id=18, repointed_id=None),
            SimpleNamespace(id=19, repointed_id=None),
        ]

    merged_data = SimpleNamespace(
        owners=None,
        operators=None,
        name="Merged Field",
        country="ZZZ",
        name_local=None,
        state_province=None,
        region=None,
        basin=None,
        reservoir_formation=None,
        latitude=None,
        longitude=None,
        discovery_year=None,
        production_start_year=None,
        fid_year=None,
        location_type=None,
        production_conventionality=None,
        primary_hydrocarbon_group=None,
        field_status=None,
    )
    raw_provenance = {
        "name": ("Merged Field", "gem"),
        "country": ("ZZZ", "wm"),
        "region": None,
    }

    monkeypatch.setattr(mca, "_load_candidate_model", fake_load_candidate_model)
    monkeypatch.setattr(mca, "_load_mergeable_resources", fake_load_mergeable_resources)
    monkeypatch.setattr(
        mca,
        "coalesce_og_field_resource",
        lambda source_entities, priorities: (merged_data, raw_provenance),
    )

    session.scalars.side_effect = [
        _FakeScalarResult([source_model_1, source_model_2]),
        _FakeScalarResult(["gem", "wm"]),
    ]

    view = await mca.preview_merge_candidate(session=session, candidate_id=1)

    assert view.resource_ids == [18, 19]
    assert view.data.name == "Merged Field"
    assert view.data.country == "ZZZ"
    assert view.provenance == {
        "name": "gem",
        "country": "wm",
        "region": None,
    }


@pytest.mark.anyio
async def test_preview_merge_candidate_raises_for_missing_candidate(monkeypatch):
    session = AsyncMock()

    async def fake_load_candidate_model(session_arg, candidate_id):
        raise ResourceNotFoundError(
            f"No merge candidate found for id = {candidate_id}."
        )

    monkeypatch.setattr(mca, "_load_candidate_model", fake_load_candidate_model)

    with pytest.raises(ResourceNotFoundError):
        await mca.preview_merge_candidate(session=session, candidate_id=999)


@pytest.mark.anyio
async def test_preview_merge_candidate_raises_for_non_mergeable_resources(monkeypatch):
    session = AsyncMock()

    candidate = SimpleNamespace(
        id=1,
        items=[
            SimpleNamespace(resource_id=18, position=0),
            SimpleNamespace(resource_id=19, position=1),
        ],
    )

    async def fake_load_candidate_model(session_arg, candidate_id):
        return candidate

    async def fake_load_mergeable_resources(session_arg, resource_ids):
        raise ResourceIntegrityError(
            "Cannot merge any resource that has already been merged."
        )

    monkeypatch.setattr(mca, "_load_candidate_model", fake_load_candidate_model)
    monkeypatch.setattr(mca, "_load_mergeable_resources", fake_load_mergeable_resources)

    with pytest.raises(ResourceIntegrityError):
        await mca.preview_merge_candidate(session=session, candidate_id=1)
