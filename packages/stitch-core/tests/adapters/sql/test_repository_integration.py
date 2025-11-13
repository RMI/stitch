"""Integration tests for SQL repositories working together."""

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from tests.fixtures.fixture_db_data import RESOURCE_DATA, MEMBERSHIP_DATA


class TestResourceMembershipIntegration:
    """Test interactions between Resource and Membership repositories."""

    def test_create_multiple_memberships_same_resource(
        self, db_session: Session, create_resource
    ):
        """Test creating multiple memberships for the same resource."""
        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)

        # Create first membership
        membership_id_1 = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-2024-001",
        )

        # Create second membership for same resource
        membership_id_2 = membership_repo.create(
            resource_id=resource_id,
            source="woodmac",
            source_pk="12345",
        )

        assert membership_id_1 != membership_id_2

        # Both should reference the same resource
        m1 = db_session.get(MembershipModel, membership_id_1)
        m2 = db_session.get(MembershipModel, membership_id_2)
        assert m1.resource_id == resource_id
        assert m2.resource_id == resource_id
        assert m1.source == "gem"
        assert m2.source == "woodmac"

    def test_create_membership_different_resources_same_source(
        self, db_session: Session
    ):
        """Test that the same source can belong to different resources.

        Since the design creates new memberships on merge, we **will** have a many-to-many
        relationship between source rows and resources.
        """
        resource_repo = SQLResourceRepository(db_session)
        membership_repo = SQLMembershipRepository(db_session)

        # Create two different resources
        resource_id_1 = resource_repo.create()
        resource_id_2 = resource_repo.create()

        membership_data = MEMBERSHIP_DATA["duplicate_source_different_resource"]

        # Create memberships with same source but different resources
        membership_id_1 = membership_repo.create(
            resource_id=resource_id_1,
            source=membership_data["source"],
            source_pk=membership_data["source_pk"],
        )

        membership_id_2 = membership_repo.create(
            resource_id=resource_id_2,
            source=membership_data["source"],
            source_pk=membership_data["source_pk"],
        )

        # Both memberships should exist
        m1 = db_session.get(MembershipModel, membership_id_1)
        m2 = db_session.get(MembershipModel, membership_id_2)

        assert m1.resource_id == resource_id_1
        assert m2.resource_id == resource_id_2
        assert m1.source_pk == m2.source_pk  # Same source
        assert m1.source == m2.source

    def test_create_membership_foreign_key_constraint(self, db_session: Session):
        """Test that creating a membership with non-existent resource_id fails."""
        membership_repo = SQLMembershipRepository(db_session)

        # Try to create membership with non-existent resource
        with pytest.raises(IntegrityError):
            membership_repo.create(
                resource_id=999999,  # Non-existent resource
                source="gem",
                source_pk="GEM-INVALID",
            )
            db_session.commit()

    def test_create_membership_relationship_to_resource(self, db_session: Session):
        """Test that the relationship from membership to resource works correctly."""
        resource_repo = SQLResourceRepository(db_session)
        resource_data = RESOURCE_DATA["gem_full"]
        resource_id = resource_repo.create(
            name=resource_data["name"],
            country=resource_data["country"],
        )

        membership_repo = SQLMembershipRepository(db_session)
        membership_id = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-REL-TEST",
        )

        # Access relationship
        saved_membership = db_session.get(MembershipModel, membership_id)
        related_resource = saved_membership.resource

        assert related_resource is not None
        assert related_resource.id == resource_id
        assert related_resource.name == resource_data["name"]

    def test_get_resource_includes_memberships_relationship(self, db_session: Session):
        """Test that fetching a resource includes its memberships via relationship."""
        resource_repo = SQLResourceRepository(db_session)
        membership_repo = SQLMembershipRepository(db_session)

        # Create resource
        resource_id = resource_repo.create(
            name="Test Resource",
        )

        # Create memberships for it
        membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-001",
        )
        membership_repo.create(
            resource_id=resource_id,
            source="woodmac",
            source_pk="WM-001",
        )

        # Fetch resource and check memberships relationship
        saved_resource = db_session.get(ResourceModel, resource_id)
        assert len(saved_resource.memberships) == 2
        assert saved_resource.memberships[0].resource_id == resource_id
        assert saved_resource.memberships[1].resource_id == resource_id
