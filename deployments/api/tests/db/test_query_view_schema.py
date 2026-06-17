"""Schema tests for og_field_resource_query_view.

TDD: these tests must go RED before the model/migration are created.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.model import StitchBase
from stitch.api.db.model.og_field_resource_query_view import (
    OGFieldResourceQueryView,
    VALUE_TEXT_FIELDS,
    VALUE_NUM_FIELDS,
    VALUE_JSON_FIELDS,
    FIELD_TO_VALUE_COLUMN,
)
from stitch.ogsi.model.og_field import OilGasFieldBase


def test_table_present_in_metadata():
    """og_field_resource_query_view must be registered in StitchBase.metadata."""
    assert "og_field_resource_query_view" in StitchBase.metadata.tables


def test_table_is_not_a_view():
    """The table must NOT carry info['is_view'] = True (conftest excludes view tables)."""
    table = StitchBase.metadata.tables["og_field_resource_query_view"]
    assert not table.info.get("is_view")


def test_primary_key_columns():
    """PK must be exactly {resource_id, source_id, column_name}."""
    table = StitchBase.metadata.tables["og_field_resource_query_view"]
    pk_cols = {col.name for col in table.primary_key.columns}
    assert pk_cols == {"resource_id", "source_id", "column_name"}


@pytest.mark.anyio
async def test_row_round_trips_sqlite(integration_session: AsyncSession):
    """Insert one row (using inspect to avoid FK constraints on SQLite) and select it back."""
    # SQLite doesn't enforce FKs by default, so we can insert directly
    conn = await integration_session.connection()
    table = StitchBase.metadata.tables["og_field_resource_query_view"]

    # Insert a row with value_json (a list) and value_num (a float)
    await conn.execute(
        table.insert().values(
            resource_id=1,
            source_id=1,
            column_name="owners",
            source="rmi",
            priority=1,
            value_text=None,
            value_num=None,
            value_json=[{"name": "Acme", "stake": 100.0}],
        )
    )
    await conn.execute(
        table.insert().values(
            resource_id=1,
            source_id=1,
            column_name="latitude",
            source="rmi",
            priority=1,
            value_text=None,
            value_num=45.123,
            value_json=None,
        )
    )

    result = (await conn.execute(table.select())).fetchall()
    assert len(result) == 2

    # Verify value_json round-trip
    json_row = next(r for r in result if r.column_name == "owners")
    assert json_row.value_json == [{"name": "Acme", "stake": 100.0}]

    # Verify value_num round-trip
    num_row = next(r for r in result if r.column_name == "latitude")
    assert abs(num_row.value_num - 45.123) < 1e-6


def test_field_routing_constants_cover_og_field_base():
    """VALUE_*_FIELDS union must equal OilGasFieldBase.model_fields, pairwise disjoint."""
    all_model_fields = set(OilGasFieldBase.model_fields)

    text_set = set(VALUE_TEXT_FIELDS)
    num_set = set(VALUE_NUM_FIELDS)
    json_set = set(VALUE_JSON_FIELDS)

    # Pairwise disjoint
    assert text_set.isdisjoint(num_set), f"Overlap text∩num: {text_set & num_set}"
    assert text_set.isdisjoint(json_set), f"Overlap text∩json: {text_set & json_set}"
    assert num_set.isdisjoint(json_set), f"Overlap num∩json: {num_set & json_set}"

    # Union equals model fields
    union = text_set | num_set | json_set
    assert union == all_model_fields, (
        f"Missing from routing: {all_model_fields - union}; "
        f"Extra in routing: {union - all_model_fields}"
    )

    # FIELD_TO_VALUE_COLUMN is derived correctly
    assert set(FIELD_TO_VALUE_COLUMN.keys()) == all_model_fields
    for f in VALUE_TEXT_FIELDS:
        assert FIELD_TO_VALUE_COLUMN[f] == "value_text"
    for f in VALUE_NUM_FIELDS:
        assert FIELD_TO_VALUE_COLUMN[f] == "value_num"
    for f in VALUE_JSON_FIELDS:
        assert FIELD_TO_VALUE_COLUMN[f] == "value_json"
