"""Integration tests for ResourceService.create_resource with real database.

These tests use a real SQLite database to verify that the service correctly
persists resources and memberships, and that transactions work as expected.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.sql_transaction_context import (
    SQLTransactionContext,
)
from stitch.core.resources.app.services.resource_service import ResourceService
from data.parameter_sets import UNICODE_TEST_CASES


class TestResourceServiceCreateResourceIntegration:
    """Integration tests for create_resource with real SQLite database."""

    def test_full_resource_creation_flow(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test complete resource creation with full data."""
        # Arrange
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Permian Basin Field",
            "country": "USA",
            "latitude": 32.0,
            "longitude": -102.5,
        }
        mock_source_repo.write.return_value = "gem_12345"

        # Act
        resource_entity = resource_service_integration.create_resource(
            source="gem", data={"id": "12345", "name": "Permian Basin Field"}
        )

        # Assert - verify resource created
        resource = (
            db_session.query(ResourceModel).filter_by(id=resource_entity.id).first()
        )
        assert resource is not None
        assert resource.name == "Permian Basin Field"
        assert resource.country == "USA"
        assert resource.latitude == 32.0
        assert resource.longitude == -102.5

        # Assert - verify membership created
        membership = (
            db_session.query(MembershipModel)
            .filter_by(resource_id=resource_entity.id)
            .first()
        )
        assert membership is not None
        assert membership.source == "gem"
        assert membership.source_pk == "gem_12345"

    def test_minimal_data_creation(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test resource creation with minimal required fields."""
        # Arrange - minimal data with None values
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Minimal Field",
            "country": None,
            "latitude": None,
            "longitude": None,
        }
        mock_source_repo.write.return_value = "min_001"

        # Act
        resource_entity = resource_service_integration.create_resource(
            source="test_source", data={"id": "001"}
        )

        # Assert
        resource = (
            db_session.query(ResourceModel).filter_by(id=resource_entity.id).first()
        )
        assert resource.name == "Minimal Field"
        assert resource.country is None
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
            {"name": "Field A", "country": "USA"},
            {"name": "Field B", "country": "CAN"},
            {"name": "Field C", "country": "MEX"},
        ]

        resource_ids = []

        # Act - create multiple resources
        for i, data in enumerate(resources_data):
            mock_source_repo.row_to_record_data.return_value = {
                **data,
                "latitude": None,
                "longitude": None,
            }
            mock_source_repo.write.return_value = f"source_{i}"

            resource_entity = resource_service_integration.create_resource(
                source="test_source", data={"id": str(i)}
            )
            resource_ids.append(resource_entity.id)

        # Assert - all resources created with unique IDs
        assert len(set(resource_ids)) == 3

        # Verify all persisted
        count = db_session.query(ResourceModel).count()
        assert count == 3

    @pytest.mark.parametrize("source_data,expected_fields", UNICODE_TEST_CASES)
    def test_unicode_characters_persist_correctly(
        self,
        resource_service_integration,
        db_session,
        mock_source_repo,
        source_data,
        expected_fields,
    ):
        """Verify unicode characters handled correctly by real database."""
        mock_source_repo.row_to_record_data.return_value = source_data
        mock_source_repo.write.return_value = "unicode_test"

        resource_entity = resource_service_integration.create_resource(
            source="gem", data={"id": "UNICODE_TEST"}
        )

        resource = (
            db_session.query(ResourceModel).filter_by(id=resource_entity.id).first()
        )
        assert resource is not None

        for field, expected_value in expected_fields.items():
            actual_value = getattr(resource, field)
            assert actual_value == expected_value, (
                f"Unicode field {field} mismatch: expected {expected_value!r}, got {actual_value!r}"
            )

    def test_duplicate_membership_constraint_violation(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Verify transaction rollback on duplicate membership constraint violation."""
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Test Field",
            "country": "USA",
            "latitude": 30.0,
            "longitude": -95.0,
        }
        mock_source_repo.write.return_value = "test_001"

        first_resource_entity = resource_service_integration.create_resource(
            source="test_source", data={"id": "001"}
        )

        session_factory = sessionmaker(bind=db_session.get_bind())

        def _registry_factory(session):
            registry = MagicMock()
            registry.get_source_repository.return_value = mock_source_repo
            return registry

        class DuplicateMembershipContext(SQLTransactionContext):
            """Custom context that creates duplicate membership."""

            def __enter__(self):
                super().__enter__()
                original_create = self.memberships.create

                def create_duplicate(**kwargs):
                    return original_create(
                        resource_id=first_resource_entity.id,
                        source=kwargs["source"],
                        source_pk=kwargs["source_pk"],
                    )

                self.memberships.create = create_duplicate
                return self

        tx_context = DuplicateMembershipContext(session_factory, _registry_factory)
        service = ResourceService(tx_context)

        mock_source_repo.write.return_value = "test_001"

        with pytest.raises(IntegrityError):
            service.create_resource(source="test_source", data={"id": "002"})

        check_session = session_factory()
        resource_count = check_session.query(ResourceModel).count()
        membership_count = check_session.query(MembershipModel).count()
        check_session.close()

        assert resource_count == 1
        assert membership_count == 1


class TestResourceServiceMergeResourcesIntegration:
    """Integration tests for merge_resources with real SQLite database."""

    def test_basic_merge_flow(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test merging two resources with full database verification."""
        mock_source_repo.row_to_record_data.return_value = {
            "name": "Field 1",
            "country": "USA",
            "latitude": 30.0,
            "longitude": -95.0,
        }
        mock_source_repo.write.return_value = "gem_001"

        resource1 = resource_service_integration.create_resource(
            source="gem", data={"id": "001"}
        )

        mock_source_repo.row_to_record_data.return_value = {
            "name": "Field 2",
            "country": "CAN",
            "latitude": 50.0,
            "longitude": -110.0,
        }
        mock_source_repo.write.return_value = "woodmac_002"

        resource2 = resource_service_integration.create_resource(
            source="woodmac", data={"id": "002"}
        )

        mock_gem_source = MagicMock()
        mock_wm_source = MagicMock()

        def mock_fetch(source_pk):
            if source_pk == "gem_001":
                return mock_gem_source
            elif source_pk == "woodmac_002":
                return mock_wm_source
            raise ValueError(f"Unknown source_pk: {source_pk}")

        mock_source_repo.fetch.side_effect = mock_fetch

        aggregate = resource_service_integration.merge_resources(resource1, resource2)

        assert aggregate.root is not None
        assert aggregate.root.id != resource1.id
        assert aggregate.root.id != resource2.id
        assert aggregate.constituents == (resource1, resource2)

        merged_resource = (
            db_session.query(ResourceModel).filter_by(id=aggregate.root.id).first()
        )
        assert merged_resource is not None
        assert merged_resource.name is None
        assert merged_resource.country is None

        resource1_updated = (
            db_session.query(ResourceModel).filter_by(id=resource1.id).first()
        )
        resource2_updated = (
            db_session.query(ResourceModel).filter_by(id=resource2.id).first()
        )
        assert resource1_updated.repointed_to == aggregate.root.id
        assert resource2_updated.repointed_to == aggregate.root.id

        new_memberships = (
            db_session.query(MembershipModel)
            .filter_by(resource_id=aggregate.root.id)
            .all()
        )
        assert len(new_memberships) == 2

        source_keys = {(m.source, m.source_pk) for m in new_memberships}
        assert source_keys == {("gem", "gem_001"), ("woodmac", "woodmac_002")}

        assert "gem" in aggregate.source_data
        assert "woodmac" in aggregate.source_data
        assert aggregate.source_data["gem"]["gem_001"] == mock_gem_source
        assert aggregate.source_data["woodmac"]["woodmac_002"] == mock_wm_source

    def test_merge_three_resources(
        self, resource_service_integration, db_session, mock_source_repo
    ):
        """Test merging three resources simultaneously."""
        resources = []
        source_configs = [
            ("gem", "gem_001", "Field A", "USA"),
            ("woodmac", "woodmac_002", "Field B", "CAN"),
            ("rystad", "rystad_003", "Field C", "MEX"),
        ]

        for source, source_pk, name, country in source_configs:
            mock_source_repo.row_to_record_data.return_value = {
                "name": name,
                "country": country,
                "latitude": 30.0,
                "longitude": -95.0,
            }
            mock_source_repo.write.return_value = source_pk

            resource = resource_service_integration.create_resource(
                source=source, data={"id": source_pk}
            )
            resources.append(resource)

        mock_sources = {
            "gem_001": MagicMock(),
            "woodmac_002": MagicMock(),
            "rystad_003": MagicMock(),
        }

        def mock_fetch(source_pk):
            if source_pk in mock_sources:
                return mock_sources[source_pk]
            raise ValueError(f"Unknown source_pk: {source_pk}")

        mock_source_repo.fetch.side_effect = mock_fetch

        aggregate = resource_service_integration.merge_resources(*resources)

        assert aggregate.root is not None
        assert len(aggregate.constituents) == 3
        assert set(aggregate.constituents) == set(resources)

        for resource in resources:
            updated = db_session.query(ResourceModel).filter_by(id=resource.id).first()
            assert updated.repointed_to == aggregate.root.id

        new_memberships = (
            db_session.query(MembershipModel)
            .filter_by(resource_id=aggregate.root.id)
            .all()
        )
        assert len(new_memberships) == 3

        source_keys = {(m.source, m.source_pk) for m in new_memberships}
        expected_keys = {
            ("gem", "gem_001"),
            ("woodmac", "woodmac_002"),
            ("rystad", "rystad_003"),
        }
        assert source_keys == expected_keys

    def test_transaction_rollback_on_merge_error(
        self, db_session, mock_source_registry, mock_source_repo
    ):
        """Verify transaction rolls back when merge operation fails."""
        from stitch.core.resources.adapters.sql.errors import ResourceIntegrityError

        session_factory = sessionmaker(bind=db_session.get_bind())

        def _registry_factory(session):
            return mock_source_registry

        tx_context = SQLTransactionContext(session_factory, _registry_factory)
        service = ResourceService(tx_context)

        mock_source_repo.row_to_record_data.return_value = {
            "name": "Field 1",
            "country": "USA",
            "latitude": 30.0,
            "longitude": -95.0,
        }
        mock_source_repo.write.return_value = "test_001"

        resource1 = service.create_resource(source="test_source", data={"id": "001"})

        mock_source_repo.write.return_value = "test_002"
        resource2 = service.create_resource(source="test_source", data={"id": "002"})

        initial_resource_count = db_session.query(ResourceModel).count()
        initial_membership_count = db_session.query(MembershipModel).count()

        with pytest.raises(
            ResourceIntegrityError, match="only possible between different resources"
        ):
            service.merge_resources(resource1, resource1)

        check_session = session_factory()
        final_resource_count = check_session.query(ResourceModel).count()
        final_membership_count = check_session.query(MembershipModel).count()
        check_session.close()

        assert final_resource_count == initial_resource_count
        assert final_membership_count == initial_membership_count

        resource1_check = (
            db_session.query(ResourceModel).filter_by(id=resource1.id).first()
        )
        assert resource1_check.repointed_to is None

    def test_end_to_end_merge_with_heterogeneous_sources(
        self, db_session, mock_source_registry
    ):
        """End-to-end test: merge resources with heterogeneous data from multiple sources."""
        gem_data = {
            "GEM001": {
                "name": "Permian Basin Field",
                "country": "USA",
                "latitude": 32.0,
                "longitude": -102.5,
                "operator": "ExxonMobil",
                "status": "Operating",
            },
            "GEM002": {
                "name": "North Sea Platform",
                "country": "NOR",
                "latitude": 60.5,
                "longitude": 4.2,
                "operator": "Equinor",
                "status": "Operating",
            },
        }

        woodmac_data = {
            "WM001": {
                "name": "Permian Field Complex",
                "country": "US",
                "latitude": 32.1,
                "longitude": -102.6,
                "field_type": "Onshore",
                "reserves_mmboe": 1500,
            },
            "WM002": {
                "name": "Bakken Formation",
                "country": "US",
                "latitude": None,
                "longitude": None,
                "field_type": "Shale",
                "reserves_mmboe": 2300,
            },
        }

        rystad_data = {
            "RY001": {
                "name": "West Texas Complex",
                "country": "USA",
                "latitude": 32.05,
                "longitude": -102.55,
                "discovery_year": 1920,
                "water_depth": None,
            },
            "RY002": {
                "name": "Johan Sverdrup",
                "country": "NO",
                "latitude": 58.87,
                "longitude": 2.05,
                "discovery_year": 2010,
                "water_depth": 110,
            },
        }

        source_repos = {}
        for source_name, dataset in [
            ("gem", gem_data),
            ("woodmac", woodmac_data),
            ("rystad", rystad_data),
        ]:
            repo = MagicMock()
            repo.source = source_name
            source_entities = {}
            call_tracker = {}

            for record_id, record_data in dataset.items():
                source_pk = f"{source_name}_{record_id}"
                mock_entity = MagicMock()
                mock_entity.source = source_name
                mock_entity.source_pk = source_pk
                mock_entity.data = record_data
                source_entities[source_pk] = mock_entity

            def make_row_to_record(data_map, tracker):
                def row_to_record(row):
                    record_id = row["id"]
                    rec_data = {
                        "name": data_map[record_id]["name"],
                        "country": data_map[record_id]["country"],
                        "latitude": data_map[record_id].get("latitude"),
                        "longitude": data_map[record_id].get("longitude"),
                    }
                    tracker["last_id"] = record_id
                    return rec_data

                return row_to_record

            def make_write(source_prefix, tracker):
                def write(**rec_data):
                    record_id = tracker.get("last_id")
                    return f"{source_prefix}_{record_id}"

                return write

            def make_fetch(entities_map):
                def fetch(source_pk):
                    if source_pk in entities_map:
                        return entities_map[source_pk]
                    raise ValueError(f"Unknown source_pk: {source_pk}")

                return fetch

            repo.row_to_record_data.side_effect = make_row_to_record(
                dataset, call_tracker
            )
            repo.write.side_effect = make_write(source_name, call_tracker)
            repo.fetch.side_effect = make_fetch(source_entities)
            source_repos[source_name] = (repo, source_entities)

        def get_source_repo(source_name):
            return source_repos[source_name][0]

        mock_source_registry.get_source_repository.side_effect = get_source_repo

        session_factory = sessionmaker(bind=db_session.get_bind())

        def _registry_factory(session):
            return mock_source_registry

        tx_context = SQLTransactionContext(session_factory, _registry_factory)
        service = ResourceService(tx_context)

        gem_resource = service.create_resource(source="gem", data={"id": "GEM001"})
        woodmac_resource = service.create_resource(
            source="woodmac", data={"id": "WM001"}
        )
        rystad_resource = service.create_resource(source="rystad", data={"id": "RY001"})

        aggregate = service.merge_resources(
            gem_resource, woodmac_resource, rystad_resource
        )

        assert aggregate.root is not None
        assert aggregate.root.id is not None
        assert len(aggregate.constituents) == 3
        assert set(aggregate.constituents) == {
            gem_resource,
            woodmac_resource,
            rystad_resource,
        }

        assert len(aggregate.source_data) == 3
        assert "gem" in aggregate.source_data
        assert "woodmac" in aggregate.source_data
        assert "rystad" in aggregate.source_data

        gem_source_entity = aggregate.source_data["gem"]["gem_GEM001"]
        assert gem_source_entity.source == "gem"
        assert gem_source_entity.source_pk == "gem_GEM001"
        assert gem_source_entity.data["operator"] == "ExxonMobil"
        assert gem_source_entity.data["status"] == "Operating"

        woodmac_source_entity = aggregate.source_data["woodmac"]["woodmac_WM001"]
        assert woodmac_source_entity.source == "woodmac"
        assert woodmac_source_entity.source_pk == "woodmac_WM001"
        assert woodmac_source_entity.data["field_type"] == "Onshore"
        assert woodmac_source_entity.data["reserves_mmboe"] == 1500

        rystad_source_entity = aggregate.source_data["rystad"]["rystad_RY001"]
        assert rystad_source_entity.source == "rystad"
        assert rystad_source_entity.source_pk == "rystad_RY001"
        assert rystad_source_entity.data["discovery_year"] == 1920
        assert rystad_source_entity.data["water_depth"] is None

        check_session = session_factory()
        merged_resource = (
            check_session.query(ResourceModel).filter_by(id=aggregate.root.id).first()
        )
        assert merged_resource is not None
        assert merged_resource.repointed_to is None

        for constituent in aggregate.constituents:
            resource = (
                check_session.query(ResourceModel).filter_by(id=constituent.id).first()
            )
            assert resource.repointed_to == aggregate.root.id

        all_memberships = check_session.query(MembershipModel).all()
        merged_memberships = [
            m for m in all_memberships if m.resource_id == aggregate.root.id
        ]
        assert len(merged_memberships) == 3

        membership_keys = {(m.source, m.source_pk) for m in merged_memberships}
        expected_keys = {
            ("gem", "gem_GEM001"),
            ("woodmac", "woodmac_WM001"),
            ("rystad", "rystad_RY001"),
        }
        assert membership_keys == expected_keys

        check_session.close()
