"""Unit tests for ResourceService.create_resource with mocked dependencies.

These tests focus on verifying the service orchestration logic without
database interaction. All dependencies are mocked to test the service's
behavior in isolation.
"""

import pytest

from tests.utils.assertions import (
    assert_resource_created_with,
    assert_membership_created_with,
    assert_transaction_entered_and_exited,
    get_create_kwargs,
)


class TestResourceServiceCreateResourceUnit:
    """Unit tests for create_resource with mocked dependencies."""

    def test_create_resource_orchestration(
        self,
        resource_service,
        mock_transaction_context,
    ):
        """Verify repositories are called in correct sequence with correct arguments."""
        test_data = {"id": "TEST123", "name": "Test"}

        result = resource_service.create_resource(source="test_source", data=test_data)

        assert_transaction_entered_and_exited(mock_transaction_context)

        mock_transaction_context.source_registry.get_source_repository.assert_called_once_with(
            "test_source"
        )

        source_repo = mock_transaction_context.source_registry.get_source_repository.return_value
        source_repo.row_to_record_data.assert_called_once_with(test_data)
        source_repo.write.assert_called_once()

        assert_resource_created_with(
            mock_transaction_context,
            dataset="test_source",
            source_pk="source_123",
            name="Test Resource",
            country_iso3="USA",
            operator="Test Operator",
            latitude=30.0,
            longitude=-95.0,
        )

        assert_membership_created_with(
            mock_transaction_context,
            resource_id=42,
            source_name="test_source",
            source_id="source_123",
        )

        assert result == 42

    def test_transaction_context_usage(self, resource_service, mock_transaction_context):
        """Verify transaction context manager is used correctly."""
        resource_service.create_resource(source="test_source", data={"id": "TEST"})

        assert_transaction_entered_and_exited(mock_transaction_context)

    def test_data_transformation(
        self, resource_service, mock_transaction_context
    ):
        """Verify source data is correctly transformed to resource data."""
        source_repo = mock_transaction_context.source_registry.get_source_repository.return_value
        source_repo.row_to_record_data.return_value = {
            "dataset": "test_source",
            "payload": {"id": "CUSTOM"},
            "name": "Custom Name",
            "country_iso3": "CAN",
            "operator": "Custom Operator",
            "latitude": 45.5,
            "longitude": -73.5,
        }

        resource_service.create_resource(source="test_source", data={"id": "X"})

        assert_resource_created_with(
            mock_transaction_context,
            name="Custom Name",
            country_iso3="CAN",
            operator="Custom Operator",
            latitude=45.5,
            longitude=-73.5,
            dataset="test_source",
        )

    def test_source_write_failure_propagates(
        self, resource_service, mock_transaction_context
    ):
        """Verify exception from source write propagates correctly."""
        source_repo = mock_transaction_context.source_registry.get_source_repository.return_value
        source_repo.write.side_effect = ValueError("Source write failed")

        with pytest.raises(ValueError, match="Source write failed"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        mock_transaction_context.resources.create.assert_not_called()
        mock_transaction_context.memberships.create.assert_not_called()

    def test_returns_resource_id(self, resource_service, mock_transaction_context):
        """Verify service returns the resource ID from repository."""
        mock_transaction_context.resources.create.return_value = 999

        result = resource_service.create_resource(source="test_source", data={"id": "TEST"})

        assert result == 999


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
            resource_service.create_resource(source="unknown_source", data={"id": "TEST"})

        mock_transaction_context.resources.create.assert_not_called()
        mock_transaction_context.memberships.create.assert_not_called()

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
        source_repo = mock_transaction_context.source_registry.get_source_repository.return_value
        source_repo.row_to_record_data.side_effect = ValueError(
            "Invalid data format"
        )

        with pytest.raises(ValueError, match="Invalid data format"):
            resource_service.create_resource(source="test_source", data={"id": "TEST"})

        source_repo.write.assert_not_called()
        mock_transaction_context.resources.create.assert_not_called()
        mock_transaction_context.memberships.create.assert_not_called()


class TestResourceServiceDataScenarios:
    """Parameterized tests for different data scenarios."""

    @pytest.mark.parametrize(
        "source_data,expected_fields",
        [
            (
                {
                    "dataset": "gem",
                    "payload": {"id": "GEM123"},
                    "name": "Test Field",
                    "country_iso3": "USA",
                    "operator": "TestCo",
                    "latitude": 30.0,
                    "longitude": -95.0,
                },
                {
                    "name": "Test Field",
                    "country_iso3": "USA",
                    "operator": "TestCo",
                    "latitude": 30.0,
                    "longitude": -95.0,
                },
            ),
            (
                {
                    "dataset": "woodmac",
                    "payload": {"field_id": "WM456"},
                    "name": "Offshore Platform",
                    "country_iso3": "NOR",
                    "operator": None,
                    "latitude": 60.5,
                    "longitude": 4.5,
                },
                {
                    "name": "Offshore Platform",
                    "country_iso3": "NOR",
                    "latitude": 60.5,
                    "longitude": 4.5,
                },
            ),
            (
                {
                    "dataset": "custom_source",
                    "payload": {"custom_id": "CS789"},
                    "name": None,
                    "country_iso3": None,
                    "operator": None,
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
        source_repo = mock_transaction_context.source_registry.get_source_repository.return_value
        source_repo.row_to_record_data.return_value = source_data

        resource_service.create_resource(
            source=source_data["dataset"], data={"id": "TEST"}
        )

        if expected_fields:
            assert_resource_created_with(
                mock_transaction_context, dataset=source_data["dataset"], **expected_fields
            )
        else:
            mock_transaction_context.resources.create.assert_called_once()

    @pytest.mark.parametrize(
        "resource_id_input,expected_result",
        [
            (None, 42),
            (100, 42),
            (999, 42),
        ],
    )
    def test_resource_id_handling(
        self,
        resource_service,
        mock_transaction_context,
        resource_id_input,
        expected_result,
    ):
        """Verify resource_id parameter is handled correctly."""
        result = resource_service.create_resource(
            source="test_source", data={"id": "TEST"}, resource_id=resource_id_input
        )

        assert result == expected_result

    @pytest.mark.parametrize(
        "source_name",
        ["gem", "woodmac", "custom_source", "test-source-123"],
    )
    def test_handles_different_source_names(
        self,
        resource_service,
        mock_transaction_context,
        source_name,
    ):
        """Verify service handles different source names."""
        resource_service.create_resource(source=source_name, data={"id": "TEST"})

        mock_transaction_context.source_registry.get_source_repository.assert_called_once_with(
            source_name
        )
        assert_membership_created_with(
            mock_transaction_context,
            resource_id=42,
            source_name=source_name,
            source_id="source_123",
        )
