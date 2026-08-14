"""Unit tests for resources router with mocked dependencies."""

import csv
import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from stitch.ogsi.model import OGFieldListItemView, OilGasFieldBase

from stitch.api.db.config import get_uow
from stitch.api.main import app
from stitch.api.routers.oil_gas_fields import CSV_EXPORT_ROW_LIMIT

from tests.factories import ResourceCreateFactory, SourceFactory


class TestGetResourceUnit:
    """Unit tests for GET /resources/{id} endpoint."""

    @pytest.mark.anyio
    async def test_returns_resource_when_found(
        self,
        async_client,
        mock_uow,
        og_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """GET /resources/{id} returns resource from repository."""
        expected = og_res_fact(
            id=42,
            empty=False,
            view=OilGasFieldBase(name="Found Resource", country="USA"),
        )

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(return_value=expected)

            response = await async_client.get("/oil-gas-fields/42")

        assert response.status_code == 200
        view_data = response.json()
        assert view_data["id"] == 42
        assert view_data["name"] == "Found Resource"

    @pytest.mark.anyio
    async def test_returns_404_when_not_found(self, async_client, mock_uow):
        """GET /resources/{id} returns 404 when resource not found."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(
                side_effect=HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail="No Resource with id `999` found.",
                )
            )

            response = await async_client.get("/oil-gas-fields/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]


class TestCreateResourceUnit:
    """Unit tests for POST /resources/ endpoint."""

    @pytest.mark.anyio
    async def test_creates_resource_with_user(
        self,
        async_client,
        mock_uow,
        test_user,
        og_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """POST /resources/ calls repo.create with user and data."""
        src = source_maker(id=1, source="wm")
        expected = og_res_fact(id=123, source_data=[src])
        in_src = source_maker(source="wm", name="New Resource")
        resource_in = og_res_fact(empty=True, source_data=[in_src])

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post(
                "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
            )

        assert response.status_code == 200
        mock_repo.create.assert_awaited_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["user"].id == test_user.id
        assert call_kwargs["resource"].id is None
        assert len(call_kwargs["resource"].source_data) == 1

    @pytest.mark.anyio
    async def test_returns_created_resource(
        self,
        async_client,
        mock_uow,
        source_maker: SourceFactory,
        og_res_fact: ResourceCreateFactory,
    ):
        """POST /resources/ returns the created resource entity."""
        src = source_maker(id=1, source="wm", name="Created Resource")
        expected = og_res_fact(id=456, source_data=[src])
        src_in = source_maker(managed=False, source="wm", name="Created Resource")
        resource_in = og_res_fact(empty=True, source_data=[src_in])

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post(
                "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 456
        assert data.get("view", None) is None
        assert len((source_data := data.get("source_data", []))) == 1
        assert source_data[0]["name"] == "Created Resource"
        assert "source_record" not in source_data[0]

    @pytest.mark.anyio
    async def test_validates_request_body(self, async_client, mock_uow):
        """POST /resources/ returns 422 for invalid request body with bad source_data."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        response = await async_client.post("/oil-gas-fields/", json={"label": 123})

        assert response.status_code == 422


class TestGetAllResourcesUnit:
    """Unit tests for GET /oil-gas-fields/ paginated endpoint."""

    @pytest.mark.anyio
    async def test_returns_paginated_response(
        self,
        async_client,
        mock_uow,
    ):
        """GET /oil-gas-fields/ returns envelope with items and metadata."""
        list_items = [
            OGFieldListItemView(
                id=i,
                data=OilGasFieldBase(name=f"R{i}", country=None),
                provenance={"name": "rmi"},
            )
            for i in range(10, 13)
        ]

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.query = AsyncMock(return_value=(list_items, 3))

            response = await async_client.get("/oil-gas-fields/")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["items"]) == 3

    @pytest.mark.anyio
    async def test_passes_pagination_params(
        self,
        async_client,
        mock_uow,
    ):
        """GET /oil-gas-fields/?page=2&page_size=10 passes params to query."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.query = AsyncMock(return_value=([], 0))

            response = await async_client.get("/oil-gas-fields/?page=2&page_size=10")

        assert response.status_code == 200
        mock_repo.query.assert_awaited_once()
        call_kwargs = mock_repo.query.call_args.kwargs
        params = call_kwargs["params"]
        assert params.offset == 10
        assert params.limit == 10


class TestGetResourceFilterOptionsUnit:
    """Unit tests for GET /oil-gas-fields/filter-options endpoint."""

    @pytest.mark.anyio
    async def test_returns_filter_options(self, async_client, mock_uow):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.filter_options = AsyncMock(return_value=["CAN", "USA"])

            response = await async_client.get(
                "/oil-gas-fields/filter-options?field=country"
            )

        assert response.status_code == 200
        assert response.json() == {"field": "country", "values": ["CAN", "USA"]}

    @pytest.mark.anyio
    async def test_passes_licensed_sources_and_source_filters(
        self,
        async_client,
        mock_uow,
    ):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.filter_options = AsyncMock(return_value=["CAN", "USA"])

            response = await async_client.get(
                "/oil-gas-fields/filter-options?field=country&source=gem&source=wm"
            )

        assert response.status_code == 200
        mock_repo.filter_options.assert_awaited_once()
        call_kwargs = mock_repo.filter_options.call_args.kwargs
        assert call_kwargs["licensed_sources"] == frozenset(
            {"rmi", "gem", "wm", "ccr", "alb", "bc", "llm"}
        )
        assert call_kwargs["params"].field == "country"
        assert call_kwargs["params"].source == ["gem", "wm"]


class TestExportResourcesCsvUnit:
    """Unit tests for GET /oil-gas-fields/export/csv endpoint."""

    _LIST_ITEMS = [
        OGFieldListItemView(
            id=1,
            data=OilGasFieldBase(
                name="Burgan Field",
                country="KWT",
                region="Middle East",
                basin="Arabian",
                field_status="Producing",
            ),
            provenance={"name": "gem", "country": "gem"},
        ),
        OGFieldListItemView(
            id=2,
            data=OilGasFieldBase(name="Ghawar Field", country="SAU"),
            provenance={"name": "wm", "country": "wm"},
        ),
    ]

    @pytest.mark.anyio
    async def test_returns_csv_content_type(self, async_client, mock_uow):
        """GET /export/csv returns text/csv content type."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=(self._LIST_ITEMS, 2))

            response = await async_client.get("/oil-gas-fields/export/csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    @pytest.mark.anyio
    async def test_response_has_attachment_content_disposition(
        self, async_client, mock_uow
    ):
        """Content-Disposition header marks the response as a file attachment."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=(self._LIST_ITEMS, 2))

            response = await async_client.get("/oil-gas-fields/export/csv")

        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "stitch-export-" in disposition
        assert disposition.endswith('.csv"')

    @pytest.mark.anyio
    async def test_csv_contains_expected_headers(self, async_client, mock_uow):
        """The CSV response starts with an ``id`` header and all field columns."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=(self._LIST_ITEMS, 2))

            response = await async_client.get("/oil-gas-fields/export/csv")

        reader = csv.DictReader(io.StringIO(response.text))
        fieldnames = reader.fieldnames or []
        assert "id" in fieldnames
        assert "name" in fieldnames
        assert "country" in fieldnames
        assert "latitude" in fieldnames
        assert "owners" in fieldnames
        assert "field_status" in fieldnames
        assert "name_source" in fieldnames
        assert "country_source" in fieldnames

    @pytest.mark.anyio
    async def test_csv_contains_resource_data(self, async_client, mock_uow):
        """Each resource appears as a row with correct field values."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=(self._LIST_ITEMS, 2))

            response = await async_client.get("/oil-gas-fields/export/csv")

        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["id"] == "1"
        assert rows[0]["name"] == "Burgan Field"
        assert rows[0]["country"] == "KWT"
        assert rows[0]["name_source"] == "gem"
        assert rows[1]["id"] == "2"
        assert rows[1]["name"] == "Ghawar Field"

    @pytest.mark.anyio
    async def test_empty_result_returns_headers_only(self, async_client, mock_uow):
        """An empty result set returns a CSV with only the header row."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=([], 0))

            response = await async_client.get("/oil-gas-fields/export/csv")

        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        assert len(rows) == 0
        assert "id" in (reader.fieldnames or [])

    @pytest.mark.anyio
    async def test_returns_400_when_over_row_limit(self, async_client, mock_uow):
        """Returns HTTP 400 with an informative message when total_count exceeds the limit."""
        over_limit_count = CSV_EXPORT_ROW_LIMIT + 1

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            # Return empty items but an over-limit total_count.
            mock_repo.export = AsyncMock(return_value=([], over_limit_count))

            response = await async_client.get("/oil-gas-fields/export/csv")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert str(over_limit_count) in detail.replace(",", "")

    @pytest.mark.anyio
    async def test_filename_hash_differs_for_different_filters(
        self, async_client, mock_uow
    ):
        """Different query params produce different filename hashes."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=(self._LIST_ITEMS, 2))

            resp_a = await async_client.get("/oil-gas-fields/export/csv")
            resp_b = await async_client.get("/oil-gas-fields/export/csv?country=USA")

        disp_a = resp_a.headers.get("content-disposition", "")
        disp_b = resp_b.headers.get("content-disposition", "")
        assert disp_a != disp_b

    @pytest.mark.anyio
    async def test_passes_filter_params_to_action(self, async_client, mock_uow):
        """Query params are forwarded to the export action."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.export = AsyncMock(return_value=([], 0))

            await async_client.get("/oil-gas-fields/export/csv?country=USA&q=ghawar")

        mock_repo.export.assert_awaited_once()
        call_kwargs = mock_repo.export.call_args.kwargs
        assert call_kwargs["params"].country == "USA"
        assert call_kwargs["params"].q == "ghawar"
