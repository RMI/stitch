"""Tests for SQLMembershipRepository."""

from datetime import datetime
import time

import pytest
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)
from stitch.core.resources.adapters.sql.model.membership import (
    MembershipModel,
)
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
