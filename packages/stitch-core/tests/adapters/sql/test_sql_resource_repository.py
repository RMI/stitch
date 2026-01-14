"""Tests for SQLResourceRepository."""

import pytest
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.errors import (
    EntityNotFoundError,
    ResourceIntegrityError,
)
from fixtures.fixture_db_data import RESOURCE_DATA


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

    def test_get_resource_raises_for_nonexistent_id(self, db_session: Session):
        """Test that get() returns None for non-existent resource."""
        repo = SQLResourceRepository(db_session)

        with pytest.raises(EntityNotFoundError) as exc_info:
            repo.get(999999)

        assert "999999" in str(exc_info.value)


class TestSQLResourceRepositoryMergeResources:
    """Test suite for SQLResourceRepository.merge_resources() method."""

    def test_merge_creates_new_resource_with_higher_id_attributes(
        self, db_session: Session
    ):
        """Test that merge creates new resource with attributes from higher ID resource."""
        repo = SQLResourceRepository(db_session)

        # Create two resources with different attributes
        id1 = repo.create(
            name="Resource One",
            country="Country A",
            latitude=10.0,
            longitude=20.0,
        )
        id2 = repo.create(
            name="Resource Two",
            country="Country B",
            latitude=30.0,
            longitude=40.0,
        )

        # Merge them
        new_resource, *_ = repo.merge_resources(id1, id2)

        # Verify new resource was created
        assert new_resource is not None
        assert new_resource.id is not None
        assert new_resource.id != id1
        assert new_resource.id != id2

        # New resource should have attributes from higher ID (id2)
        # assert new_resource.name == None
        # assert new_resource.country == None
        # assert new_resource.
        # assert pytest.approx(new_resource.latitude, rel=1e-6) == 30.0
        # assert pytest.approx(new_resource.longitude, rel=1e-6) == 40.0

        # Both original resources should be repointed to new resource
        saved_r1 = db_session.get(ResourceModel, id1)
        saved_r2 = db_session.get(ResourceModel, id2)

        assert saved_r1.repointed_to == new_resource.id
        assert saved_r2.repointed_to == new_resource.id

        # New resource itself should not be repointed
        saved_new = db_session.get(ResourceModel, new_resource.id)
        assert saved_new.repointed_to is None

    def test_merge_accepts_different_input_types(self, db_session: Session):
        """Test that merge_resources accepts int and ResourceEntity inputs."""
        repo = SQLResourceRepository(db_session)

        # Create three pairs of resources for testing different input combinations
        # Pair 1: both ints
        id1_a = repo.create(name="Resource 1A")
        id1_b = repo.create(name="Resource 1B")

        # Pair 2: first as int, second as entity
        id2_a = repo.create(name="Resource 2A")
        id2_b = repo.create(name="Resource 2B")
        entity2_b = repo.get(id2_b)

        # Pair 3: first as entity, second as int
        id3_a = repo.create(name="Resource 3A")
        id3_b = repo.create(name="Resource 3B")
        entity3_a = repo.get(id3_a)

        # Test 1: both ints
        result1, *_ = repo.merge_resources(id1_a, id1_b)
        assert result1 is not None
        assert result1.id is not None

        # Verify repointing happened
        saved1_a = db_session.get(ResourceModel, id1_a)
        saved1_b = db_session.get(ResourceModel, id1_b)
        assert saved1_a.repointed_to == result1.id
        assert saved1_b.repointed_to == result1.id

        # Test 2: int and ResourceEntity
        result2, *_ = repo.merge_resources(id2_a, entity2_b)
        assert result2 is not None
        assert result2.id is not None

        saved2_a = db_session.get(ResourceModel, id2_a)
        saved2_b = db_session.get(ResourceModel, id2_b)
        assert saved2_a.repointed_to == result2.id
        assert saved2_b.repointed_to == result2.id

        # Test 3: ResourceEntity and int
        result3, *_ = repo.merge_resources(entity3_a, id3_b)
        assert result3 is not None
        assert result3.id is not None

        saved3_a = db_session.get(ResourceModel, id3_a)
        saved3_b = db_session.get(ResourceModel, id3_b)
        assert saved3_a.repointed_to == result3.id
        assert saved3_b.repointed_to == result3.id

    def test_merge_same_id_raises_resource_integrity_error(self, db_session: Session):
        """Test that attempting to merge a resource with itself raises ResourceIntegrityError."""
        repo = SQLResourceRepository(db_session)

        # Create a resource
        resource_id = repo.create(name="Test Resource")

        # Attempt to merge it with itself should raise error
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(resource_id, resource_id)

        # Verify error message contains the ID
        error_message = str(exc_info.value)
        assert "only possible between different resources" in error_message
        assert str(resource_id) in error_message

    def test_merge_nonexistent_resources_raises_resource_integrity_error(
        self, db_session: Session
    ):
        """Test that merging with non-existent resources raises ResourceIntegrityError."""
        repo = SQLResourceRepository(db_session)

        # Create one real resource
        real_id = repo.create(name="Real Resource")

        # Test 1: Non-existent left resource
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(999999, real_id)

        error_message = str(exc_info.value)
        assert "Multiple Resources required for merging" in error_message
        assert "999999" in error_message

        # Test 2: Non-existent right resource
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(real_id, 888888)

        error_message = str(exc_info.value)
        assert "Multiple Resources required for merging" in error_message
        assert "888888" in error_message

        # Test 3: Both non-existent
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(111111, 222222)

        error_message = str(exc_info.value)
        assert "Multiple Resources required for merging" in error_message
        # Both IDs should be in the error message
        assert "111111" in error_message
        assert "222222" in error_message

    def test_merge_already_merged_resource_raises_integrity_error(
        self, db_session: Session
    ):
        """Test that attempting to merge an already-merged resource raises ResourceIntegrityError."""
        repo = SQLResourceRepository(db_session)

        # Create three resources
        id_a = repo.create(name="Resource A")
        id_b = repo.create(name="Resource B")
        id_c = repo.create(name="Resource C")

        # Merge A and B to create merged resource AB
        merged_ab, *_ = repo.merge_resources(id_a, id_b)

        # Now A and B are both repointed to merged_ab
        # Try to merge A again (left parameter)
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(id_a, id_c)

        error_message = str(exc_info.value)
        assert "Cannot merge any resource that has already been merged" in error_message
        assert "Repointed" in error_message

        # Try to merge B again (right parameter)
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(id_c, id_b)

        error_message = str(exc_info.value)
        assert "Cannot merge any resource that has already been merged" in error_message
        assert "Repointed" in error_message

        # Create another pair and merge them
        id_d = repo.create(name="Resource D")
        id_e = repo.create(name="Resource E")
        merged_de, *_ = repo.merge_resources(id_d, id_e)

        # Try to merge two already-merged resources
        with pytest.raises(ResourceIntegrityError) as exc_info:
            repo.merge_resources(id_a, id_d)

        error_message = str(exc_info.value)
        assert "Cannot merge any resource that has already been merged" in error_message

    def test_merge_resources_with_special_data(self, db_session: Session):
        """Test merging resources with special characters, unicode, and null coordinates."""
        repo = SQLResourceRepository(db_session)

        # Test with unicode/special characters
        # Regular resource created first (will have lower ID)
        id_regular = repo.create(
            name="Regular Name",
            country="USA",
            latitude=10.0,
            longitude=20.0,
        )

        # Special chars resource created second (will have higher ID)
        special_chars_data = RESOURCE_DATA["edge_case_special_chars"]
        id_special = repo.create(**special_chars_data)

        # Merge them (special has higher ID, so its attributes should be selected)
        merged1, *_ = repo.merge_resources(id_regular, id_special)
        # assert merged1.name == special_chars_data["name"]
        # assert merged1.country == special_chars_data["country"]

        # Test with null coordinates
        # Resource with location created first (lower ID)
        id_with_loc = repo.create(
            name="With Location",
            country="USA",
            latitude=30.0,
            longitude=40.0,
        )

        # Resource without location created second (higher ID)
        no_location_data = RESOURCE_DATA["edge_case_no_location"]
        id_no_loc = repo.create(**no_location_data)

        # Merge them (no_location has higher ID)
        merged2, *_ = repo.merge_resources(id_with_loc, id_no_loc)
        assert merged2.name is None
        assert merged2.country is None
        assert merged2.latitude is None
        assert merged2.longitude is None

        # Verify both originals are repointed
        saved1 = db_session.get(ResourceModel, id_with_loc)
        saved2 = db_session.get(ResourceModel, id_no_loc)
        assert saved1.repointed_to == merged2.id
        assert saved2.repointed_to == merged2.id

    def test_merge_selection_logic(self, db_session: Session):
        """Test that merge always selects attributes from higher ID regardless of parameter order."""
        pytest.skip("Merge selection logic removed.")
        repo = SQLResourceRepository(db_session)

        # Create two resources with distinct attributes
        # First resource (lower ID)
        id_first = repo.create(
            name="First Resource",
            country="FRA",
            latitude=48.8566,
            longitude=2.3522,
        )

        # Second resource (higher ID)
        id_second = repo.create(
            name="Second Resource",
            country="USA",
            latitude=40.7128,
            longitude=-74.0060,
        )

        # Verify IDs are sequential
        assert id_second > id_first

        # Test 1: Merge with lower ID as left parameter
        merged1, *_ = repo.merge_resources(id_first, id_second)

        # Should select from second (higher ID)
        assert merged1.name == "Second Resource"
        assert merged1.country == "USA"
        assert pytest.approx(merged1.latitude, rel=1e-6) == 40.7128
        assert pytest.approx(merged1.longitude, rel=1e-6) == -74.0060

        # Create another pair for reverse order test
        id_third = repo.create(
            name="Third Resource",
            country="GBR",
            latitude=51.5074,
            longitude=-0.1278,
        )

        id_fourth = repo.create(
            name="Fourth Resource",
            country="JPN",
            latitude=35.6762,
            longitude=139.6503,
        )

        # Test 2: Merge with higher ID as left parameter
        merged2, *_ = repo.merge_resources(id_fourth, id_third)

        # Should still select from fourth (higher ID), even though it's the left parameter
        assert merged2.name == "Fourth Resource"
        assert merged2.country == "JPN"
        assert pytest.approx(merged2.latitude, rel=1e-6) == 35.6762
        assert pytest.approx(merged2.longitude, rel=1e-6) == 139.6503
