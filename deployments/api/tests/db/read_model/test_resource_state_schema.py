"""Schema and drift guards for ``og_field_resource_state``."""

import pytest
from sqlalchemy import JSON, Float, Integer, String, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.model import OGFieldResourceState, ResourceModel
from stitch.api.db.model.oil_gas_field_source_value import (
    ATTRIBUTE_KINDS,
    ATTRIBUTE_NAMES,
    ValueKind,
)
from stitch.api.entities import FILTER_OPTION_FIELDS, User

_STATE_TABLE = OGFieldResourceState.__table__
_NON_VALUE_COLUMNS = {"resource_id", "permission_mask", "provenance"}

_EXPECTED_TYPE: dict[ValueKind, type] = {
    ValueKind.TEXT: String,
    ValueKind.INT: Integer,
    ValueKind.FLOAT: Float,
    ValueKind.JSON: JSON,
}


def test_value_columns_match_flattened_attributes():
    value_columns = set(_STATE_TABLE.columns.keys()) - _NON_VALUE_COLUMNS
    assert value_columns == set(ATTRIBUTE_NAMES)


@pytest.mark.parametrize("field", ATTRIBUTE_NAMES)
def test_value_column_type_follows_attribute_kind(field: str):
    column = _STATE_TABLE.columns[field]
    assert isinstance(column.type, _EXPECTED_TYPE[ATTRIBUTE_KINDS[field]])
    assert column.nullable


def test_primary_key_is_resource_and_mask():
    assert [c.name for c in _STATE_TABLE.primary_key.columns] == [
        "resource_id",
        "permission_mask",
    ]


def test_resource_fk_cascades():
    [fk] = _STATE_TABLE.c.resource_id.foreign_keys
    assert fk.target_fullname == "og_field_resources.id"
    assert fk.ondelete == "CASCADE"


def _index_columns() -> set[tuple[str, ...]]:
    return {tuple(c.name for c in index.columns) for index in _STATE_TABLE.indexes}


@pytest.mark.parametrize("field", FILTER_OPTION_FIELDS)
def test_each_filter_option_field_has_a_mask_leading_index(field: str):
    assert ("permission_mask", field) in _index_columns()


def test_single_profile_and_default_sort_indexes():
    indexes = _index_columns()
    assert ("permission_mask", "resource_id") in indexes
    assert ("permission_mask", "name", "resource_id") in indexes


async def _new_resource(session: AsyncSession, user: User) -> int:
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()
    return resource.id


@pytest.mark.anyio
async def test_typed_values_round_trip(
    seeded_integration_session: AsyncSession, test_user: User
):
    session = seeded_integration_session
    rid = await _new_resource(session, test_user)
    owners = [{"name": "Acme", "share": 0.6}, {"name": "Globex", "share": 0.4}]
    provenance = {name: None for name in ATTRIBUTE_NAMES} | {
        "name": "gem",
        "owners": "wm",
        "latitude": "rmi",
        "discovery_year": "ccr",
    }
    session.add(
        OGFieldResourceState(
            resource_id=rid,
            permission_mask=3,
            name="Alpha",
            owners=owners,
            operators=["Acme Ops"],
            latitude=12.5,
            discovery_year=1987,
            provenance=provenance,
        )
    )
    await session.commit()
    session.expunge_all()

    row = await session.get(OGFieldResourceState, (rid, 3))
    assert row is not None
    assert row.name == "Alpha"
    assert row.owners == owners
    assert row.operators == ["Acme Ops"]
    assert row.latitude == 12.5
    assert row.discovery_year == 1987
    assert row.provenance == provenance
    assert row.country is None


@pytest.mark.anyio
async def test_unset_json_value_is_sql_null(
    seeded_integration_session: AsyncSession, test_user: User
):
    """An unset JSON field must be SQL NULL, not JSON ``null``, so it matches
    ``IS NULL`` / ``NULLS LAST`` the same way the live path's absent row does."""
    session = seeded_integration_session
    rid = await _new_resource(session, test_user)
    session.add(
        OGFieldResourceState(
            resource_id=rid, permission_mask=0, owners=None, provenance={}
        )
    )
    await session.commit()

    is_null = await session.scalar(
        text(
            "SELECT owners IS NULL FROM og_field_resource_state WHERE resource_id = :id"
        ).bindparams(id=rid)
    )
    assert is_null


@pytest.mark.anyio
@pytest.mark.parametrize("mask", [-1, 4])
async def test_permission_mask_out_of_range_is_rejected(
    seeded_integration_session: AsyncSession, test_user: User, mask: int
):
    session = seeded_integration_session
    rid = await _new_resource(session, test_user)
    session.add(
        OGFieldResourceState(resource_id=rid, permission_mask=mask, provenance={})
    )
    with pytest.raises(IntegrityError):
        await session.flush()
