"""Tests for SQLResourceRepository."""

import pytest
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from tests.fixtures.fixture_db_data import RESOURCE_DATA


class TestSQLResourceRepositoryCreate:
    """Test suite for SQLResourceRepository.create() method."""

    @pytest.mark.parametrize(
        "fixture_key",
        ["gem_full", "gem_minimal", "woodmac_full"],
    )
    def test_create_resource_basic_scenarios(
        self, db_session: Session, fixture_key: str
    ):
        """Test creating resources with various field combinations."""
        repo = SQLResourceRepository(db_session)
        data = RESOURCE_DATA[fixture_key]

        resource_id = repo.create(**data)

        assert resource_id is not None
        assert isinstance(resource_id, int)

        # Verify resource was saved correctly
        saved = db_session.get(ResourceModel, resource_id)
        assert saved is not None
        assert saved.created is not None
        assert saved.memberships == []

        # Verify optional fields match input
        for field in ["name", "country", "latitude", "longitude"]:
            expected = data.get(field)
            actual = getattr(saved, field)
            if expected is not None and field in ["latitude", "longitude"]:
                assert pytest.approx(float(actual), rel=1e-6) == expected
            else:
                assert actual == expected

    def test_create_multiple_resources(self, db_session: Session):
        """Test creating multiple resources in sequence."""
        repo = SQLResourceRepository(db_session)

        id1 = repo.create()
        id2 = repo.create()
        id3 = repo.create()

        # All IDs should be unique
        assert len({id1, id2, id3}) == 3

        # All resources should exist in database
        assert all(db_session.get(ResourceModel, i) for i in [id1, id2, id3])

    def test_create_resource_with_repointed_to(self, db_session: Session):
        """Test creating a resource with repointed_to set (for merge scenarios)."""
        repo = SQLResourceRepository(db_session)

        # Create parent resource first
        parent_id = repo.create(
            name="Parent Resource",
        )

        assert parent_id is not None

        # Create child resource pointing to parent
        child_id = repo.create(
            repointed_to=parent_id,
            name="Child Resource",
        )

        saved_child = db_session.get(ResourceModel, child_id)
        assert saved_child.repointed_to == parent_id

    def test_resource_created_timestamp_is_set_automatically(self, db_session: Session):
        """Test that created timestamp is set automatically by database."""
        repo = SQLResourceRepository(db_session)

        resource_id = repo.create()

        saved = db_session.get(ResourceModel, resource_id)
        assert saved.created is not None
        # Verify it's a recent timestamp (within last minute)
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        # Handle both timezone-aware and naive datetimes
        created = saved.created
        if created.tzinfo is None:
            # If database returns naive datetime, assume UTC
            created = created.replace(tzinfo=timezone.utc)

        age = now - created
        assert timedelta(0) <= age < timedelta(seconds=20)


class TestSQLResourceRepositoryGet:
    """Test suite for SQLResourceRepository.get() method."""

    def test_get_resource_returns_entity_with_correct_attributes(
        self, db_session: Session
    ):
        """Test fetching a resource returns entity with correct attributes."""
        repo = SQLResourceRepository(db_session)
        data = RESOURCE_DATA["gem_full"]

        # Create resource
        resource_id = repo.create(**data)
        db_session.commit()

        # Fetch it back
        entity = repo.get(resource_id)

        assert entity is not None
        assert entity.id == resource_id
        assert entity.name == data["name"]
        assert entity.country == data["country"]
        assert pytest.approx(entity.latitude, rel=1e-6) == data["latitude"]
        assert pytest.approx(entity.longitude, rel=1e-6) == data["longitude"]

    def test_get_resource_returns_none_for_nonexistent_id(self, db_session: Session):
        """Test that get() returns None for non-existent resource."""
        repo = SQLResourceRepository(db_session)

        result = repo.get(999999)

        assert result is None
