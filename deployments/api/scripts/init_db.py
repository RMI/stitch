"""
Generate SQL DDL and seed data for stitch-api database.

Uses SQLAlchemy ORM models exclusively - if model definitions change,
simply regenerate the SQL file.

Usage:
    uv run --package stitch-api python deployments/api/scripts/init_db.py > deployments/api/scripts/init.sql
"""

import json
from typing import Any

from sqlalchemy import inspect, insert, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from stitch.api.db.model import (
    CCReservoirsSourceModel,
    GemSourceModel,
    MembershipModel,
    MembershipStatus,
    RMIManualSourceModel,
    ResourceModel,
    StitchBase,
    UserModel,
    WMSourceModel,
)
from stitch.api.entities import (
    CCReservoirsData,
    GemData,
    RMIManualData,
    User as UserEntity,
    WMData,
)


def get_model_values(model: Any) -> dict[str, Any]:
    """Extract column values from an ORM model instance.

    Handles special cases:
    - JSON/JSONB: converts to SQL literal with ::jsonb cast
    - Enums: converts to string value
    - Columns with server_default and None value: excluded to use DB default
    """
    from enum import Enum

    mapper = inspect(model.__class__)
    values = {}
    for col in mapper.columns:
        val = getattr(model, col.key)

        # Skip columns with server_default if value is None (let DB use default)
        if val is None and col.server_default is not None:
            continue

        # Handle JSON/JSONB types
        type_name = col.type.__class__.__name__
        impl_name = getattr(
            getattr(col.type, "impl", None), "__class__", type(None)
        ).__name__
        if type_name in ("JSON", "JSONB") or impl_name in ("JSON", "JSONB"):
            if val is not None:
                val = text(f"'{json.dumps(val)}'::jsonb")

        # Handle Enum types - wrap in text() to bypass SQLAlchemy's enum rendering
        elif isinstance(val, Enum):
            val = text(f"'{val.value}'")

        values[col.key] = val
    return values


def compile_insert(model: Any) -> str:
    """Compile an INSERT statement for an ORM model instance."""
    values = get_model_values(model)
    model_class = model.__class__
    stmt = insert(model_class).values(**values)

    dialect = postgresql.dialect()
    compiled = stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True})

    return str(compiled) + ";"


def generate_ddl() -> list[str]:
    """Generate CREATE TABLE statements from ORM model metadata."""
    statements = []
    dialect = postgresql.dialect()

    # Create enum type for MembershipStatus
    enum_values = ", ".join(f"'{s.value}'" for s in MembershipStatus)
    statements.append(f"CREATE TYPE membershipstatus AS ENUM ({enum_values});")

    for table in StitchBase.metadata.sorted_tables:
        create_stmt = CreateTable(table).compile(dialect=dialect)
        statements.append(str(create_stmt).strip() + ";")

        for index in table.indexes:
            index_stmt = CreateIndex(index).compile(dialect=dialect)
            statements.append(str(index_stmt).strip() + ";")

    return statements


def create_seed_user() -> UserModel:
    """Create seed user for audit fields."""
    return UserModel(
        id=1,
        first_name="Seed",
        last_name="User",
        email="seed@example.com",
    )


def create_seed_sources() -> tuple[
    list[GemSourceModel],
    list[WMSourceModel],
    list[RMIManualSourceModel],
    list[CCReservoirsSourceModel],
]:
    """Create seed source data using Pydantic entities and ORM from_entity()."""
    gem_sources = [
        GemSourceModel.from_entity(
            GemData(name="Permian Basin Field", country="USA", lat=31.8, lon=-102.3)
        ),
        GemSourceModel.from_entity(
            GemData(name="North Sea Platform", country="GBR", lat=57.5, lon=1.5)
        ),
    ]
    # Set explicit IDs for seed data
    for i, src in enumerate(gem_sources, start=1):
        src.id = i

    wm_sources = [
        WMSourceModel.from_entity(
            WMData(
                field_name="Eagle Ford Shale", field_country="USA", production=125000.5
            )
        ),
        WMSourceModel.from_entity(
            WMData(field_name="Ghawar Field", field_country="SAU", production=500000.0)
        ),
    ]
    for i, src in enumerate(wm_sources, start=1):
        src.id = i

    rmi_sources = [
        RMIManualSourceModel.from_entity(
            RMIManualData(
                name_override="Custom Override Name",
                gwp=25.5,
                gor=0.45,
                country="CAN",
                latitude=56.7,
                longitude=-111.4,
            )
        ),
    ]
    for i, src in enumerate(rmi_sources, start=1):
        src.id = i

    cc_sources = [
        CCReservoirsSourceModel.from_entity(
            CCReservoirsData(
                name="Alberta Deep Basin",
                basin="Western Canadian Sedimentary",
                depth=3500.0,
                geofence=[
                    (56.0, -115.0),
                    (56.0, -110.0),
                    (54.0, -110.0),
                    (54.0, -115.0),
                ],
            )
        ),
    ]
    for i, src in enumerate(cc_sources, start=1):
        src.id = i

    return gem_sources, wm_sources, rmi_sources, cc_sources


def create_seed_resources(user: UserEntity) -> list[ResourceModel]:
    """Create seed resources using ORM factory method."""
    resources = [
        ResourceModel.create(user, name="Multi-Source Asset", country="USA"),
        ResourceModel.create(user, name="Single Source Asset", country="GBR"),
    ]
    for i, res in enumerate(resources, start=1):
        res.id = i
    return resources


def create_seed_memberships(
    user: UserEntity,
    resources: list[ResourceModel],
    gem_sources: list[GemSourceModel],
    wm_sources: list[WMSourceModel],
    rmi_sources: list[RMIManualSourceModel],
) -> list[MembershipModel]:
    """Create seed memberships linking resources to sources."""
    memberships = [
        # Resource 1 has 3 memberships (multi-source)
        MembershipModel.create(user, resources[0], "gem", gem_sources[0].id),
        MembershipModel.create(user, resources[0], "wm", wm_sources[0].id),
        MembershipModel.create(user, resources[0], "rmi", rmi_sources[0].id),
        # Resource 2 has 1 membership
        MembershipModel.create(user, resources[1], "gem", gem_sources[1].id),
    ]
    for i, mem in enumerate(memberships, start=1):
        mem.id = i
    return memberships


def generate_seed_data() -> list[str]:
    """Generate INSERT statements from ORM model instances."""
    statements = []

    # Create seed user
    user_model = create_seed_user()
    statements.append(compile_insert(user_model))

    # Create UserEntity for factory methods that need it
    user_entity = UserEntity(
        id=user_model.id,
        email=user_model.email,
        name=f"{user_model.first_name} {user_model.last_name}",
    )

    # Create sources
    gem_sources, wm_sources, rmi_sources, cc_sources = create_seed_sources()
    for src in gem_sources + wm_sources + rmi_sources + cc_sources:
        statements.append(compile_insert(src))

    # Create resources
    resources = create_seed_resources(user_entity)
    for res in resources:
        statements.append(compile_insert(res))

    # Create memberships
    memberships = create_seed_memberships(
        user_entity, resources, gem_sources, wm_sources, rmi_sources
    )
    for mem in memberships:
        statements.append(compile_insert(mem))

    return statements


def generate_sequence_resets() -> list[str]:
    """Generate sequence reset statements for tables with explicit ID inserts."""
    tables = [
        "users",
        "gem_sources",
        "wm_sources",
        "rmi_manual_sources",
        "cc_reservoirs_sources",
        "resources",
        "memberships",
    ]
    return [
        f"SELECT setval('{t}_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM {t}), false);"
        for t in tables
    ]


def main():
    print("-- Generated by init_db.py")
    print("-- DDL for stitch-api models (uses SQLAlchemy ORM introspection)")
    print()

    ddl = generate_ddl()
    for stmt in ddl:
        print(stmt)
        print()

    print("-- Seed data (generated from ORM model instances)")
    print()

    seed = generate_seed_data()
    for stmt in seed:
        print(stmt)
        print()

    print("-- Reset sequences after explicit ID inserts")
    print()

    seq_resets = generate_sequence_resets()
    for stmt in seq_resets:
        print(stmt)
        print()


if __name__ == "__main__":
    main()
