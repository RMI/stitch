"""Tests for SQLAlchemy relationships between ResourceModel and MembershipModel.

These tests verify that the bidirectional relationships between resources
and memberships work correctly, including lazy loading and the identity map.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.model.membership import MembershipModel


class TestResourceMembershipRelationships:
    """Test SQLAlchemy relationships between ResourceModel and MembershipModel."""

    def test_resource_memberships_relationship(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test ResourceModel.memberships relationship loads correctly."""
        # Arrange
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Test Resource",
            "country": "USA",
            "operator": "TestCo",
            "latitude": 30.0,
            "longitude": -95.0,
        }
        mock_source_repo.write.return_value = "source_123"

        # Act - create resource via service
        resource_id = resource_service_integration.create_resource(
            source="test_source", data={"id": "TEST123"}
        )

        # Load ResourceModel directly to test relationship
        resource = db_session.query(ResourceModel).filter_by(id=resource_id).first()

        # Assert - access memberships relationship (triggers lazy load)
        memberships = resource.memberships
        assert len(memberships) == 1
        assert memberships[0].resource_id == resource.id
        assert memberships[0].dataset == "test_source"
        assert memberships[0].source_pk == "source_123"

    def test_membership_resource_relationship(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test MembershipModel.resource relationship loads correctly."""
        # Arrange
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Relationship Test",
            "country": "CAN",
            "operator": "CanadaCo",
            "latitude": 45.0,
            "longitude": -75.0,
        }
        mock_source_repo.write.return_value = "can_456"

        # Act - create resource
        resource_id = resource_service_integration.create_resource(
            source="woodmac", data={"id": "456"}
        )

        # Load MembershipModel directly to test relationship
        membership = (
            db_session.query(MembershipModel).filter_by(resource_id=resource_id).first()
        )

        # Assert - access resource relationship (triggers lazy load)
        resource = membership.resource
        assert resource.id == resource_id
        assert resource.name == "Relationship Test"
        assert resource.country == "CAN"
        assert resource.operator == "CanadaCo"
        assert resource.dataset == "woodmac"

    def test_cascade_behavior_multiple_memberships(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test multiple memberships on same resource via relationships."""
        # Arrange - create resource with first membership
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Multi-Source Field",
            "country": "USA",
            "operator": "MultiCo",
            "latitude": 35.0,
            "longitude": -100.0,
        }
        mock_source_repo.write.return_value = "first_789"

        resource_id = resource_service_integration.create_resource(
            source="gem", data={"id": "789"}
        )

        # Add second membership manually (simulating merge scenario)
        session_factory = sessionmaker(bind=db_session.get_bind())
        repo_session = session_factory()
        member_repo = SQLMembershipRepository(repo_session)

        member_repo.create(
            resource_id=resource_id, source="woodmac", source_id="second_999"
        )
        repo_session.commit()

        # Act - load resource and check relationships
        resource = db_session.query(ResourceModel).filter_by(id=resource_id).first()

        # Assert - should have 2 memberships
        assert len(resource.memberships) == 2

        # Both should reference same resource instance (SQLAlchemy identity map)
        assert resource.memberships[0].resource is resource.memberships[1].resource

        # Verify different sources
        sources = {m.dataset for m in resource.memberships}
        assert sources == {"gem", "woodmac"}

        # Verify both memberships link back to resource
        for membership in resource.memberships:
            assert membership.resource.id == resource_id
