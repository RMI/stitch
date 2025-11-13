"""Unit tests for ResourceService.create_resource with mocked dependencies.

These tests focus on verifying the service orchestration logic without
database interaction. All dependencies are mocked to test the service's
behavior in isolation.
"""

import pytest

from stitch.core.resources.errors import InvalidDataTypeError, MalformedSourceDataError
from tests.data.parameter_sets import (
    DATA_TYPE_ERROR_CASES,
    MALFORMED_DATA_CASES,
    UNICODE_TEST_CASES,
)
from tests.utils.assertions import (
    assert_membership_created_with,
    assert_no_downstream_calls,
    assert_resource_created_with,
    assert_transaction_entered_and_exited,
    get_create_kwargs,
)
from tests.utils.mock_helpers import configure_source_mock


class TestResourceServiceCreateResourceUnit:
    """Unit tests for create_resource with mocked dependencies."""

    def test_create_resource_orchestration(
        self,
        resource_service,
        mock_transaction_context,
    ):
        """Verify repositories are called in correct sequence with correct arguments."""
        test_data = {"id": "TEST123", "name": "Test"}
        source_repo = configure_source_mock(
            mock_transaction_context,
            {
                "source": "test_source",
                "name": "Test Resource",
                "country": "USA",
                "latitude": 30.0,
                "longitude": -95.0,
            },
        )

        result = resource_service.create_resource(source="test_source", data=test_data)

        assert_transaction_entered_and_exited(mock_transaction_context)

        mock_transaction_context.source_registry.get_source_repository.assert_called_once_with(
            "test_source"
        )
        source_repo.row_to_record_data.assert_called_once_with(test_data)
        source_repo.write.assert_called_once()

        assert_resource_created_with(
            mock_transaction_context,
            name="Test Resource",
            country="USA",
            latitude=30.0,
            longitude=-95.0,
        )

        assert_membership_created_with(
            mock_transaction_context,
            resource_id=42,
            source="test_source",
            source_pk="source_123",
        )

        # Verify that result is a ResourceEntity with the expected ID
        assert result.id == 42
        mock_transaction_context.resources.get.assert_called_once_with(resource_id=42)

    def test_transaction_context_usage(
        self, resource_service, mock_transaction_context
    ):
        """Verify transaction context manager is used correctly."""
        resource_service.create_resource(source="test_source", data={"id": "TEST"})

        assert_transaction_entered_and_exited(mock_transaction_context)

    def test_data_transformation(self, resource_service, mock_transaction_context):
        """Verify source data is correctly transformed to resource data."""
        configure_source_mock(
            mock_transaction_context,
            {
                "source": "test_source",
                "payload": {"id": "CUSTOM"},
                "name": "Custom Name",
                "country": "CAN",
                "latitude": 45.5,
                "longitude": -73.5,
            },
        )

        resource_service.create_resource(source="test_source", data={"id": "X"})

        assert_resource_created_with(
            mock_transaction_context,
            name="Custom Name",
            country="CAN",
            latitude=45.5,
            longitude=-73.5,
        )

    def test_source_write_failure_propagates(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception from source write propagates correctly."""
        configure_source_mock(
            mock_transaction_context,
            {"source": "test", "name": "Test"},
            write_error=ValueError("Source write failed"),
        )

        with pytest.raises(ValueError, match="Source write failed"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        assert_no_downstream_calls(mock_transaction_context)

    def test_returns_resource_entity(self, resource_service, mock_transaction_context):
        """Verify service returns ResourceEntity from repository."""
        from stitch.core.resources.domain.entities import ResourceEntity
        from datetime import datetime, timezone

        mock_entity = ResourceEntity(
            id=999,
            repointed_to=None,
            name="Test",
            country="USA",
            latitude=30.0,
            longitude=-95.0,
            created=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
            created_by=None,
        )
        mock_transaction_context.resources.create.return_value = 999
        mock_transaction_context.resources.get.return_value = mock_entity

        result = resource_service.create_resource(
            source="test_source", data={"id": "TEST"}
        )

        assert result == mock_entity
        assert result.id == 999


class TestResourceServiceErrorHandling:
    """Unit tests for error handling scenarios."""

    def test_source_not_found_propagates_exception(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception when source repository not found."""
        mock_transaction_context.source_registry.get_source_repository.side_effect = (
            KeyError("Source 'unknown_source' not found in registry")
        )

        with pytest.raises(KeyError, match="unknown_source"):
            resource_service.create_resource(
                source="unknown_source", data={"id": "TEST"}
            )

        assert_no_downstream_calls(mock_transaction_context)

    def test_resource_creation_failure_propagates(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception from resource repository propagates correctly."""
        mock_transaction_context.resources.create.side_effect = ValueError(
            "Invalid resource data"
        )

        with pytest.raises(ValueError, match="Invalid resource data"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        mock_transaction_context.memberships.create.assert_not_called()

    def test_membership_creation_failure_propagates(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception from membership repository propagates correctly."""
        mock_transaction_context.memberships.create.side_effect = ValueError(
            "Invalid membership data"
        )

        with pytest.raises(ValueError, match="Invalid membership data"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        mock_transaction_context.resources.create.assert_called_once()

    def test_row_to_record_data_failure_propagates(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception from data transformation propagates correctly."""
        source_repo = configure_source_mock(
            mock_transaction_context, {"source": "test", "name": "Test"}
        )
        source_repo.row_to_record_data.side_effect = ValueError("Invalid data format")

        with pytest.raises(ValueError, match="Invalid data format"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        source_repo.write.assert_not_called()
        assert_no_downstream_calls(mock_transaction_context)


class TestResourceServiceDataScenarios:
    """Parameterized tests for different data scenarios."""

    @pytest.mark.parametrize(
        "source_data,expected_fields",
        [
            (
                {
                    "source": "gem",
                    "payload": {"id": "GEM123"},
                    "name": "Test Field",
                    "country": "USA",
                    "latitude": 30.0,
                    "longitude": -95.0,
                },
                {
                    "name": "Test Field",
                    "country": "USA",
                    "latitude": 30.0,
                    "longitude": -95.0,
                },
            ),
            (
                {
                    "source": "woodmac",
                    "payload": {"field_id": "WM456"},
                    "name": "Offshore Platform",
                    "country": "NOR",
                    "latitude": 60.5,
                    "longitude": 4.5,
                },
                {
                    "name": "Offshore Platform",
                    "country": "NOR",
                    "latitude": 60.5,
                    "longitude": 4.5,
                },
            ),
            (
                {
                    "source": "custom_source",
                    "payload": {"custom_id": "CS789"},
                    "name": None,
                    "country": None,
                    "latitude": None,
                    "longitude": None,
                },
                {},
            ),
        ],
    )
    def test_handles_various_data_formats(
        self,
        resource_service,
        mock_transaction_context,
        source_data,
        expected_fields,
    ):
        """Verify service handles different data formats and optional fields."""
        configure_source_mock(mock_transaction_context, source_data)

        resource_service.create_resource(
            source=source_data["source"], data={"id": "TEST"}
        )

        if expected_fields:
            assert_resource_created_with(
                mock_transaction_context,
                **expected_fields,
            )
        else:
            mock_transaction_context.resources.create.assert_called_once()

    @pytest.mark.parametrize(
        "source",
        ["gem", "woodmac", "custom_source", "test-source-123"],
    )
    def test_handles_different_sources(
        self,
        resource_service,
        mock_transaction_context,
        source,
    ):
        """Verify service handles different source names."""
        resource_service.create_resource(source=source, data={"id": "TEST"})

        mock_transaction_context.source_registry.get_source_repository.assert_called_once_with(
            source
        )
        assert_membership_created_with(
            mock_transaction_context,
            resource_id=42,
            source=source,
            source_pk="source_123",
        )


class TestResourceServiceUnicodeHandling:
    """Unit tests for unicode character handling in resource data."""

    @pytest.mark.parametrize("source_data,expected_fields", UNICODE_TEST_CASES)
    def test_handles_unicode_characters(
        self,
        resource_service,
        mock_transaction_context,
        source_data,
        expected_fields,
    ):
        """Verify service correctly handles unicode characters in resource fields."""
        configure_source_mock(mock_transaction_context, source_data)

        result = resource_service.create_resource(source="gem", data={"id": "TEST"})

        assert_resource_created_with(
            mock_transaction_context,
            **expected_fields,
        )
        assert result.id == 42


class TestResourceServiceDataTypeValidation:
    """Unit tests for data type validation errors."""

    @pytest.mark.parametrize(
        "source_data,error_type,field_name", DATA_TYPE_ERROR_CASES
    )
    def test_invalid_data_type_raises_error(
        self,
        resource_service,
        mock_transaction_context,
        source_data,
        error_type,
        field_name,
    ):
        """Verify service raises InvalidDataTypeError for incorrect field types."""
        source_repo = configure_source_mock(
            mock_transaction_context, source_data, write_error=error_type(f"Invalid type for {field_name}")
        )
        source_repo.row_to_record_data.side_effect = error_type(
            f"Invalid type for {field_name}"
        )

        with pytest.raises(error_type, match=field_name):
            resource_service.create_resource(
                source=source_data["dataset"], data={"id": "TEST"}
            )

        assert_no_downstream_calls(mock_transaction_context)


class TestResourceServiceMalformedDataHandling:
    """Unit tests for malformed source data handling."""

    @pytest.mark.parametrize("source_data,error_type,error_msg", MALFORMED_DATA_CASES)
    def test_malformed_data_raises_error(
        self,
        resource_service,
        mock_transaction_context,
        source_data,
        error_type,
        error_msg,
    ):
        """Verify service raises MalformedSourceDataError for invalid data structure."""
        source_repo = configure_source_mock(
            mock_transaction_context, source_data, write_error=error_type(error_msg)
        )
        source_repo.row_to_record_data.side_effect = error_type(error_msg)

        with pytest.raises(error_type, match=error_msg):
            resource_service.create_resource(source="gem", data={"id": "TEST"})

        assert_no_downstream_calls(mock_transaction_context)
