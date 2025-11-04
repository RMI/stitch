"""Reusable mock fixtures for unit testing with pytest's monkeypatch.

This module provides mock fixtures that can be used with monkeypatch to test
service layer components without database dependencies.
"""

from unittest.mock import MagicMock
import pytest

from stitch.core.resources.domain.ports import (
    ResourceRepository,
    MembershipRepository,
    SourcePersistenceRepository,
    TransactionContext,
)


@pytest.fixture
def mock_resource_repository():
    """Mock ResourceRepository with standard return values.

    Returns a MagicMock with ResourceRepository spec and default behaviors:
    - create() returns resource_id=42
    - All other methods are mocked but not configured
    """
    repo = MagicMock(spec=ResourceRepository)
    repo.create.return_value = 42
    return repo


@pytest.fixture
def mock_membership_repository():
    """Mock MembershipRepository with standard return values.

    Returns a MagicMock with MembershipRepository spec and default behaviors:
    - create() returns membership_id=1
    - All other methods are mocked but not configured
    """
    repo = MagicMock(spec=MembershipRepository)
    repo.create.return_value = 1
    return repo


@pytest.fixture
def mock_source_persistence_repository():
    """Mock SourcePersistenceRepository with standard behavior.

    Returns a MagicMock with SourcePersistenceRepository spec and default behaviors:
    - source_name property returns "test_source"
    - row_to_record_data() returns dict with all mapped fields
    - write() returns "source_123"
    """
    repo = MagicMock(spec=SourcePersistenceRepository)
    repo.source_name = "test_source"
    repo.row_to_record_data.return_value = {
        "dataset": "test_source",
        "payload": {"id": "TEST123"},
        "name": "Test Resource",
        "country_iso3": "USA",
        "operator": "Test Operator",
        "latitude": 30.0,
        "longitude": -95.0,
    }
    repo.write.return_value = "source_123"
    return repo


@pytest.fixture
def mock_source_registry_builder(mock_source_persistence_repository):
    """Factory for creating mock SourceRegistry instances.

    Returns a callable that creates a MagicMock SourceRegistry.
    The registry's get_source_repository() returns the provided source repo mock.

    Args:
        mock_source_persistence_repository: The source repo mock to return

    Returns:
        Callable that creates a configured mock SourceRegistry
    """
    def _create_registry(source_repo=None):
        if source_repo is None:
            source_repo = mock_source_persistence_repository

        registry = MagicMock()
        registry.get_source_repository.return_value = source_repo
        return registry

    return _create_registry


@pytest.fixture
def mock_transaction_context(
    mock_resource_repository,
    mock_membership_repository,
    mock_source_registry_builder,
):
    """Mock TransactionContext configured as a context manager.

    Returns a MagicMock that:
    - Implements context manager protocol (__enter__, __exit__)
    - Has .resources, .memberships, and .source_registry attributes
    - All repositories are properly mocked and configured

    This fixture is the primary mock for unit testing services that use
    the transaction context pattern.
    """
    mock_tx = MagicMock(spec=TransactionContext)

    # Configure context manager behavior
    mock_tx.__enter__ = MagicMock(return_value=mock_tx)
    mock_tx.__exit__ = MagicMock(return_value=None)

    # Attach repository mocks
    mock_tx.resources = mock_resource_repository
    mock_tx.memberships = mock_membership_repository
    mock_tx.source_registry = mock_source_registry_builder()

    return mock_tx


@pytest.fixture
def resource_service(mock_transaction_context):
    """ResourceService instance with mocked transaction context.

    Provides a fully configured ResourceService for unit testing.
    All dependencies are mocked via the mock_transaction_context fixture.

    Returns:
        ResourceService instance ready for testing
    """
    from stitch.core.resources.app.services.resource_service import ResourceService

    return ResourceService(mock_transaction_context)
