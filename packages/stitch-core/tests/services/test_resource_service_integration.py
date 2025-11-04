"""Integration tests for ResourceService.create_resource with real database.

These tests use a real SQLite database to verify that the service correctly
persists resources and memberships, and that transactions work as expected.
"""

from unittest.mock import MagicMock
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

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
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.model.membership import MembershipModel


class TestResourceServiceCreateResourceIntegration:
    """Integration tests for create_resource with real SQLite database."""

    def test_full_resource_creation_flow(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test complete resource creation with full data."""
        # Arrange
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Permian Basin Field",
            "country_iso3": "USA",
            "operator": "ExxonMobil",
            "latitude": 32.0,
            "longitude": -102.5,
        }
        mock_source_repo.write.return_value = "gem_12345"

        # Act
        resource_id = resource_service_integration.create_resource(
            source="gem", data={"id": "12345", "name": "Permian Basin Field"}
        )

        # Assert - verify resource created
        resource = db_session.query(ResourceModel).filter_by(id=resource_id).first()
        assert resource is not None
        assert resource.name == "Permian Basin Field"
        assert resource.country_iso3 == "USA"
        assert resource.operator == "ExxonMobil"
        assert resource.latitude == 32.0
        assert resource.longitude == -102.5
        assert resource.dataset == "gem"
        assert resource.source_pk == "gem_12345"

        # Assert - verify membership created
        membership = (
            db_session.query(MembershipModel)
            .filter_by(resource_id=resource_id)
            .first()
        )
        assert membership is not None
        assert membership.dataset == "gem"
        assert membership.source_pk == "gem_12345"

    def test_minimal_data_creation(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test resource creation with minimal required fields."""
        # Arrange - minimal data with None values
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Minimal Field",
            "country_iso3": None,
            "operator": None,
            "latitude": None,
            "longitude": None,
        }
        mock_source_repo.write.return_value = "min_001"

        # Act
        resource_id = resource_service_integration.create_resource(
            source="test_source", data={"id": "001"}
        )

        # Assert
        resource = db_session.query(ResourceModel).filter_by(id=resource_id).first()
        assert resource.name == "Minimal Field"
        assert resource.country_iso3 is None
        assert resource.operator is None
        assert resource.latitude is None
        assert resource.longitude is None

    def test_transaction_rollback_on_failure(
        self, db_session, mock_source_registry, mock_source_repo
    ):
        """Test that transaction rolls back when membership creation fails."""
        session_factory = sessionmaker(bind=db_session.get_bind())

        def _registry_factory(session):
            return mock_source_registry

        class FailingMembershipTransactionContext(SQLTransactionContext):
            """Custom context that injects a failing membership repository."""

            def __enter__(self):
                super().__enter__()
                member_repo = MagicMock()
                member_repo.create.side_effect = IntegrityError("Duplicate", {}, None)
                self.memberships = member_repo
                return self

        tx_context = FailingMembershipTransactionContext(
            session_factory, _registry_factory
        )
        service = ResourceService(tx_context)

        with pytest.raises(IntegrityError):
            service.create_resource(source="test_source", data={"id": "TEST"})

        check_session = session_factory()
        count = check_session.query(ResourceModel).count()
        check_session.close()
        assert count == 0

    def test_multiple_resource_creation(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test creating multiple resources independently."""
        # Arrange
        resources_data = [
            {"name": "Field A", "country_iso3": "USA"},
            {"name": "Field B", "country_iso3": "CAN"},
            {"name": "Field C", "country_iso3": "MEX"},
        ]

        resource_ids = []

        # Act - create multiple resources
        for i, data in enumerate(resources_data):
            mock_source_repo.row_to_record_data.return_value = {
                **data,
                "operator": None,
                "latitude": None,
                "longitude": None,
            }
            mock_source_repo.write.return_value = f"source_{i}"

            resource_id = resource_service_integration.create_resource(
                source="test_source", data={"id": str(i)}
            )
            resource_ids.append(resource_id)

        # Assert - all resources created with unique IDs
        assert len(set(resource_ids)) == 3

        # Verify all persisted
        count = db_session.query(ResourceModel).count()
        assert count == 3
