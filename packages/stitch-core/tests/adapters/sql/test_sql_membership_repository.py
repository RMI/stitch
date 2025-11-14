"""Tests for SQLMembershipRepository."""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)
from stitch.core.resources.adapters.sql.model.membership import (
    MembershipModel,
)
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.errors import MembershipIntegrityError
from tests.fixtures.fixture_db_data import MEMBERSHIP_DATA


class TestSQLMembershipRepositoryCreate:
    """Test suite for SQLMembershipRepository.create() method."""

    def test_create_membership_basic(self, db_session: Session, create_resource):
        """Test creating a basic membership."""
        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)
        membership_data = MEMBERSHIP_DATA["gem_active"]

        membership_id = membership_repo.create(
            resource_id=resource_id,
            source=membership_data["source"],
            source_pk=membership_data["source_pk"],
        )

        assert membership_id is not None
        assert isinstance(membership_id, int)

        # Verify the membership was created
        saved_membership = db_session.get(MembershipModel, membership_id)
        assert saved_membership is not None
        assert saved_membership.resource_id == resource_id
        assert saved_membership.source == membership_data["source"]
        assert saved_membership.source_pk == membership_data["source_pk"]
        assert saved_membership.created is not None
        assert isinstance(saved_membership.created, datetime)

    def test_create_membership_sets_timestamp(
        self, db_session: Session, create_resource
    ):
        """Test that create() automatically sets created timestamp via database default."""
        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)

        membership_id = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-TIMESTAMP",
        )

        saved_membership = db_session.get(MembershipModel, membership_id)
        assert saved_membership.created is not None
        # Verify it's a recent timestamp
        from datetime import timezone, timedelta

        now = datetime.now(timezone.utc)

        # Handle both timezone-aware and naive datetimes
        created = saved_membership.created
        if created.tzinfo is None:
            # If database returns naive datetime, assume UTC
            created = created.replace(tzinfo=timezone.utc)

        age = now - created
        assert timedelta(0) <= age < timedelta(minutes=1)

    def test_create_membership_with_nullable_fields(
        self, db_session: Session, create_resource
    ):
        """Test creating a membership without created_by and status (nullable fields)."""
        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)

        membership_id = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-NULLABLE",
        )

        saved_membership = db_session.get(MembershipModel, membership_id)
        # These fields should be None (nullable)
        assert saved_membership.created_by is None
        assert saved_membership.status is None

    def test_membership_unique_constraint_prevents_duplicates(
        self, db_session: Session, create_resource
    ):
        """Test that unique constraint prevents duplicate (resource_id, source, source_pk)."""
        from sqlalchemy.exc import IntegrityError

        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)

        # Create first membership
        membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-UNIQUE",
        )
        db_session.commit()

        # Attempt to create duplicate should fail
        with pytest.raises(IntegrityError):
            membership_repo.create(
                resource_id=resource_id,
                source="gem",
                source_pk="GEM-UNIQUE",
            )
            db_session.commit()


class TestSQLMembershipRepositoryGet:
    """Test suite for SQLMembershipRepository.get() method."""

    def test_get_membership_by_id(self, db_session: Session, create_resource):
        """Test fetching a membership by ID."""
        resource_id = create_resource()

        membership_repo = SQLMembershipRepository(db_session)
        membership_id = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="GEM-GET",
        )
        db_session.commit()

        # Fetch it back
        entity = membership_repo.get(membership_id)

        assert entity is not None
        assert entity.id == membership_id
        assert entity.resource_id == resource_id
        assert entity.source == "gem"
        assert entity.source_pk == "GEM-GET"

    def test_get_membership_nonexistent_returns_none(self, db_session: Session):
        """Test that get() returns None for non-existent membership."""
        membership_repo = SQLMembershipRepository(db_session)

        result = membership_repo.get(999999)

        assert result is None


class TestSQLMembershipRepositoryCreateRepointedMemberships:
    """Tests for create_repointed_memberships method."""

    @pytest.fixture
    def repo(self, db_session):
        """Create repository instance."""
        return SQLMembershipRepository(db_session)

    @pytest.fixture
    def sample_resources(self, db_session):
        """Create sample resources for testing."""
        resource1 = ResourceModel.create(
            name="Resource 1",
            country="US",
            latitude=40.0,
            longitude=-100.0,
            created_by="test",
        )
        resource2 = ResourceModel.create(
            name="Resource 2",
            country="CA",
            latitude=50.0,
            longitude=-110.0,
            created_by="test",
        )
        resource3 = ResourceModel.create(
            name="Resource 3",
            country="MX",
            latitude=25.0,
            longitude=-103.0,
            created_by="test",
        )
        db_session.add_all([resource1, resource2, resource3])
        db_session.flush()
        return resource1, resource2, resource3

    @pytest.fixture
    def sample_memberships(self, db_session, sample_resources):
        """Create sample memberships for testing."""
        resource1, resource2, resource3 = sample_resources

        # Create memberships for resource1
        mem1_1 = MembershipModel.create(
            resource_id=resource1.id,
            source="gem",
            source_pk="GEM001",
            created_by="test",
        )
        mem1_2 = MembershipModel.create(
            resource_id=resource1.id,
            source="woodmac",
            source_pk="WM001",
            created_by="test",
        )

        # Create memberships for resource2
        mem2_1 = MembershipModel.create(
            resource_id=resource2.id,
            source="gem",
            source_pk="GEM002",
            created_by="test",
        )
        mem2_2 = MembershipModel.create(
            resource_id=resource2.id,
            source="woodmac",
            source_pk="WM002",
            created_by="test",
        )

        db_session.add_all([mem1_1, mem1_2, mem2_1, mem2_2])
        db_session.flush()
        return [mem1_1, mem1_2, mem2_1, mem2_2]

    def test_create_repointed_memberships_basic(
        self, repo, db_session, sample_resources, sample_memberships
    ):
        """Test basic repointing of memberships from two resources to a new target."""
        resource1, resource2, resource3 = sample_resources
        target_resource = ResourceModel.create(
            name="Merged Resource",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        new_memberships = repo.create_repointed_memberships(
            from_resources=[resource1.id, resource2.id], to_resource=target_resource.id
        )

        assert len(new_memberships) == 4

        for membership in new_memberships:
            assert membership.resource_id == target_resource.id

        source_keys = {(m.source, m.source_pk) for m in new_memberships}
        expected_keys = {
            ("gem", "GEM001"),
            ("woodmac", "WM001"),
            ("gem", "GEM002"),
            ("woodmac", "WM002"),
        }
        assert source_keys == expected_keys

        db_session.flush()
        all_memberships = db_session.query(MembershipModel).all()
        assert len(all_memberships) == 8

        original_mems = (
            db_session.query(MembershipModel)
            .filter(MembershipModel.resource_id.in_([resource1.id, resource2.id]))
            .all()
        )
        assert len(original_mems) == 4
        for mem in original_mems:
            assert mem.status is None

    def test_create_repointed_memberships_no_memberships(
        self, repo, db_session, sample_resources
    ):
        """Test repointing when source resources have no memberships."""
        resource1, resource2, resource3 = sample_resources
        target_resource = ResourceModel.create(
            name="Target Resource",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        new_memberships = repo.create_repointed_memberships(
            from_resources=[resource3.id], to_resource=target_resource.id
        )

        assert new_memberships == []

        all_memberships = db_session.query(MembershipModel).all()
        assert len(all_memberships) == 0

    def test_create_repointed_memberships_accepts_different_input_types(
        self, repo, db_session, sample_resources, sample_memberships
    ):
        """Test that method accepts both int and Entity types for resources."""
        resource1, resource2, resource3 = sample_resources
        target_resource = ResourceModel.create(
            name="Target Resource",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        resource1_entity = resource1.as_entity()
        target_entity = target_resource.as_entity()

        new_memberships = repo.create_repointed_memberships(
            from_resources=[resource1_entity, resource2.id], to_resource=target_entity
        )

        assert len(new_memberships) == 4
        for membership in new_memberships:
            assert membership.resource_id == target_resource.id

    def test_multiple_resources_single_target(
        self, repo, db_session, sample_resources, sample_memberships
    ):
        """Test merging 3+ resources to a single target."""
        resource1, resource2, resource3 = sample_resources

        mem3 = MembershipModel.create(
            resource_id=resource3.id,
            source="rystad",
            source_pk="RY001",
            created_by="test",
        )
        db_session.add(mem3)
        db_session.flush()

        target_resource = ResourceModel.create(
            name="Mega Merged Resource",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        new_memberships = repo.create_repointed_memberships(
            from_resources=[resource1.id, resource2.id, resource3.id],
            to_resource=target_resource.id,
        )

        assert len(new_memberships) == 5

        for membership in new_memberships:
            assert membership.resource_id == target_resource.id

        source_keys = {(m.source, m.source_pk) for m in new_memberships}
        expected_keys = {
            ("gem", "GEM001"),
            ("woodmac", "WM001"),
            ("gem", "GEM002"),
            ("woodmac", "WM002"),
            ("rystad", "RY001"),
        }
        assert source_keys == expected_keys

    def test_repoint_already_repointed_membership_raises_error(
        self, repo, db_session, sample_resources
    ):
        """Test that attempting to repoint an already repointed membership raises error."""
        resource1, resource2, _ = sample_resources

        mem_repointed = MembershipModel.create(
            resource_id=resource1.id,
            source="gem",
            source_pk="GEM_ALREADY",
            status="REPOINTED",
            created_by="test",
        )
        db_session.add(mem_repointed)
        db_session.flush()

        target_resource = ResourceModel.create(
            name="Target",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        with pytest.raises(MembershipIntegrityError) as exc_info:
            repo.create_repointed_memberships(
                from_resources=[resource1.id], to_resource=target_resource.id
            )

        error_msg = str(exc_info.value)
        assert (
            "Cannot repoint memberships that have already been repointed" in error_msg
        )
        assert "MembershipModel" in error_msg

    def test_target_resource_with_existing_memberships_raises_error(
        self, repo, db_session, sample_resources, sample_memberships
    ):
        """Test that repointing to a resource with existing memberships raises error."""
        resource1, resource2, _ = sample_resources

        target_resource = ResourceModel.create(
            name="Target with existing membership",
            created_by="test",
        )
        db_session.add(target_resource)
        db_session.flush()

        existing_mem = MembershipModel.create(
            resource_id=target_resource.id,
            source="rystad",
            source_pk="RY999",
            created_by="test",
        )
        db_session.add(existing_mem)
        db_session.flush()

        with pytest.raises(MembershipIntegrityError) as exc_info:
            repo.create_repointed_memberships(
                from_resources=[resource1.id], to_resource=target_resource.id
            )

        error_msg = str(exc_info.value)
        assert "already has memberships" in error_msg.lower()
        assert "cannot repoint" in error_msg.lower()
