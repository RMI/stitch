"""Fixtures for testing ResourceService and related application services."""

from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session, sessionmaker

from stitch.core.resources.app.services.resource_service import ResourceService
from stitch.core.resources.adapters.sql.sql_transaction_context import (
    SQLTransactionContext,
)
from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)


@pytest.fixture
def mock_source_repo():
    """Mock SourcePersistenceRepository with standard behavior.

    Returns a mock that simulates a source-specific repository for testing.
    Default behavior transforms data and returns source IDs.
    """
    repo = MagicMock()
    repo.source_name = "test_source"
    repo.row_to_record_data.return_value = {
        "id": "TEST123",
        "name": "Test Resource",
        "country_iso3": "USA",
        "operator": "Test Operator",
        "latitude": 30.0,
        "longitude": -95.0,
    }
    repo.write.return_value = "source_123"
    return repo


@pytest.fixture
def mock_source_registry(mock_source_repo):
    """Mock SourceRegistry returning mock source repository.

    Returns a mock registry that provides access to source-specific repositories.
    """
    registry = MagicMock()
    registry.get_source_repository.return_value = mock_source_repo
    return registry


@pytest.fixture
def resource_service_integration(db_session: Session, mock_source_registry):
    """ResourceService with real repositories and mocked source registry.

    For integration tests - uses real SQLite database with actual repositories.
    Only the source registry is mocked since we don't have real source implementations.

    Args:
        db_session: SQLite session fixture from database.py
        mock_source_registry: Mock registry fixture

    Returns:
        ResourceService configured for integration testing
    """

    def _registry_factory(session: Session):
        return mock_source_registry

    # Create session factory from existing session
    session_factory = sessionmaker(bind=db_session.get_bind())
    tx_context = SQLTransactionContext(session_factory, _registry_factory)

    return ResourceService(tx_context)


@pytest.fixture
def resource_service_unit(mock_source_registry):
    """ResourceService with all mocked dependencies.

    For unit tests - no database interaction, all dependencies mocked.
    Tests focus on service orchestration logic.

    Args:
        mock_source_registry: Mock registry fixture

    Returns:
        ResourceService configured for unit testing with mocks
    """
    tx = MagicMock()
    resource_repo = MagicMock()
    resource_repo.create.return_value = 42
    member_repo = MagicMock()
    member_repo.create.return_value = 1

    return ResourceService(tx)
