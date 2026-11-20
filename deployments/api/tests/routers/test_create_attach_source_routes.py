"""Route tests for POST /oil-gas-fields/{id}/sources (create + attach)."""

from unittest.mock import AsyncMock, patch

import pytest

from stitch.api.db.errors import (
    ResourceIntegrityError,
    ResourceNotFoundError,
    SourceIntegrityError,
)
from stitch.api.db.model import ResourceModel


def _source_body() -> dict:
    return {
        "source": "rmi",
        "name": "Alpha",
        "country": "USA",
        "source_record": {
            "observed_at": "2026-01-01T00:00:00Z",
            "producer": "test",
            "payload": {},
        },
    }


@pytest.mark.anyio
async def test_creates_and_attaches_source(
    client, integration_session_factory, test_user
):
    async with integration_session_factory() as session:
        resource = ResourceModel.create(created_by=test_user)
        session.add(resource)
        await session.commit()

    response = await client.post(
        f"/oil-gas-fields/{resource.id}/sources", json=_source_body()
    )

    assert response.status_code == 200
    assert response.json()["id"] is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ResourceNotFoundError("x"), 404),
        (ResourceIntegrityError("x"), 400),
        (SourceIntegrityError("x"), 400),
        (RuntimeError("x"), 500),
    ],
)
async def test_maps_action_errors_to_status_codes(client, mock_uow, error, status):
    with patch(
        "stitch.api.routers.oil_gas_fields.og_field_source_actions"
    ) as mock_actions:
        mock_actions.create_and_attach_source = AsyncMock(side_effect=error)

        response = await client.post("/oil-gas-fields/1/sources", json=_source_body())

    assert response.status_code == status
