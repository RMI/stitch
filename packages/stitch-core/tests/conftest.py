"""Root pytest configuration for stitch-core tests.

This file makes fixtures from the fixtures/ directory available to all tests.
"""

import pytest
from sqlalchemy.orm import Session

# Import database fixtures to make them available to all tests
from fixtures.database import db_engine, db_session
from fixtures.service_fixtures import (
    mock_source_repo,
    mock_source_registry,
    resource_service_integration,
    resource_service_unit,
)
from fixtures.mocks import (
    mock_resource_repository,
    mock_membership_repository,
    mock_source_persistence_repository,
    mock_source_registry_builder,
    mock_transaction_context,
    resource_service,
)
from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)

__all__ = [
    "db_engine",
    "db_session",
    "create_resource",
    "mock_source_repo",
    "mock_source_registry",
    "resource_service_integration",
    "resource_service_unit",
    "mock_resource_repository",
    "mock_membership_repository",
    "mock_source_persistence_repository",
    "mock_source_registry_builder",
    "mock_transaction_context",
    "resource_service",
]


@pytest.fixture
def create_resource(db_session: Session):
    """Factory fixture for creating resources in tests."""

    def _create(**kwargs):
        repo = SQLResourceRepository(db_session)
        return repo.create(**kwargs)

    return _create
