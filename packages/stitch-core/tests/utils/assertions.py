"""Helper functions for making test assertions more readable and DRY."""

from typing import Any
from unittest.mock import MagicMock


def get_create_kwargs(mock_repo: MagicMock) -> dict[str, Any]:
    """Extract kwargs from the create() call on a mocked repository.

    Args:
        mock_repo: The mocked repository (resources or memberships)

    Returns:
        Dictionary of keyword arguments passed to create()
    """
    return mock_repo.create.call_args.kwargs


def assert_resource_created_with(mock_tx: MagicMock, **expected_fields):
    """Assert resource repository was called with expected fields.

    Args:
        mock_tx: Mocked transaction context
        **expected_fields: Expected field values (e.g., name="Test", source="source")
    """
    mock_tx.resources.create.assert_called_once()
    actual_kwargs = get_create_kwargs(mock_tx.resources)

    for field, expected_value in expected_fields.items():
        assert field in actual_kwargs, f"Field '{field}' not found in create() call"
        assert actual_kwargs[field] == expected_value, (
            f"Field '{field}': expected {expected_value!r}, got {actual_kwargs[field]!r}"
        )


def assert_membership_created_with(
    mock_tx: MagicMock,
    resource_id: int,
    source: str,
    source_pk: str,
):
    """Assert membership repository was called with expected values.

    Args:
        mock_tx: Mocked transaction context
        resource_id: Expected resource ID
        source: Expected source name
        source_pk: Expected source ID
    """
    mock_tx.memberships.create.assert_called_once_with(
        resource_id=resource_id,
        source=source,
        source_pk=source_pk,
    )


def assert_source_write_called(mock_tx: MagicMock):
    """Assert source repository write() was called.

    Args:
        mock_tx: Mocked transaction context
    """
    source_repo = mock_tx.source_registry.get_source_repository.return_value
    source_repo.write.assert_called_once()


def assert_transaction_entered_and_exited(mock_tx: MagicMock):
    """Assert transaction context was properly entered and exited.

    Args:
        mock_tx: Mocked transaction context
    """
    mock_tx.__enter__.assert_called_once()
    mock_tx.__exit__.assert_called_once()


def assert_no_downstream_calls(mock_tx: MagicMock):
    """Verify no repository operations were called after an error.

    Useful for testing error handling where downstream operations
    should not be executed after an exception occurs.

    Args:
        mock_tx: Mocked transaction context
    """
    mock_tx.resources.create.assert_not_called()
    mock_tx.memberships.create.assert_not_called()


def assert_resource_matches_expected(actual: Any, expected: dict[str, Any]):
    """Compare resource fields to expected data.

    Args:
        actual: The actual resource object (ORM model or entity)
        expected: Dictionary of expected field values

    Raises:
        AssertionError: If any field doesn't match expected value
    """
    for key, value in expected.items():
        actual_value = getattr(actual, key)
        assert actual_value == value, f"Field {key} mismatch: expected {value!r}, got {actual_value!r}"
