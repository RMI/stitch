"""Long (EAV) storage for OG field source attributes.

Each coalesced attribute of a source record is stored as one row here, instead
of as a column on a wide ``oil_gas_field_sources`` table. The value lives in one
of three typed columns (``value_text`` / ``value_num`` / ``value_json``) chosen
by ``ATTRIBUTE_KINDS`` -- the single source of truth mapping each
``OilGasFieldBase`` field to its physical storage. Typed columns keep Postgres's
own type system doing exact-match, substring, and numerically-correct ordering
without per-query casts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from stitch.ogsi.model.og_field import OilGasFieldBase

from .common import Base
from .types import PORTABLE_BIGINT, PORTABLE_FLOAT, PORTABLE_JSON_NULL


class ValueKind(StrEnum):
    TEXT = "text"
    INT = "int"
    FLOAT = "float"
    JSON = "json"


# Single source of truth: which physical value column backs each coalesced
# attribute of ``OilGasFieldBase`` and how to materialize it back to Python.
ATTRIBUTE_KINDS: dict[str, ValueKind] = {
    "name": ValueKind.TEXT,
    "country": ValueKind.TEXT,
    "name_local": ValueKind.TEXT,
    "state_province": ValueKind.TEXT,
    "region": ValueKind.TEXT,
    "basin": ValueKind.TEXT,
    "reservoir_formation": ValueKind.TEXT,
    "location_type": ValueKind.TEXT,
    "production_conventionality": ValueKind.TEXT,
    "primary_hydrocarbon_group": ValueKind.TEXT,
    "field_status": ValueKind.TEXT,
    "latitude": ValueKind.FLOAT,
    "longitude": ValueKind.FLOAT,
    "discovery_year": ValueKind.INT,
    "production_start_year": ValueKind.INT,
    "fid_year": ValueKind.INT,
    "owners": ValueKind.JSON,
    "operators": ValueKind.JSON,
}

# Fail fast if the registry drifts from the entity it mirrors. Use an explicit
# raise (not assert) so the check survives `python -O`.
if set(ATTRIBUTE_KINDS) != set(OilGasFieldBase.model_fields):
    raise RuntimeError(
        "ATTRIBUTE_KINDS out of sync with OilGasFieldBase fields: "
        f"{set(ATTRIBUTE_KINDS) ^ set(OilGasFieldBase.model_fields)}"
    )

ATTRIBUTE_NAMES: tuple[str, ...] = tuple(ATTRIBUTE_KINDS)

# Attributes stored as JSON (owners/operators) -- emitted as text by the list
# coalescing pivot and deserialized in Python.
JSON_ATTRIBUTE_NAMES: frozenset[str] = frozenset(
    name for name, kind in ATTRIBUTE_KINDS.items() if kind is ValueKind.JSON
)

_NUM_KINDS = frozenset({ValueKind.INT, ValueKind.FLOAT})


def value_attr_for(colname: str) -> str:
    """Return the physical column attribute name backing ``colname``."""
    kind = ATTRIBUTE_KINDS[colname]
    if kind in _NUM_KINDS:
        return "value_num"
    if kind is ValueKind.JSON:
        return "value_json"
    return "value_text"


def materialize_value(
    colname: str,
    *,
    value_text: Any,
    value_num: Any,
    value_json: Any,
) -> Any:
    """Pick + coerce the Python value for ``colname`` from typed columns."""
    kind = ATTRIBUTE_KINDS[colname]
    if kind is ValueKind.INT:
        return None if value_num is None else int(value_num)
    if kind is ValueKind.FLOAT:
        return value_num
    if kind is ValueKind.JSON:
        return value_json
    return value_text


class OilGasFieldSourceValueModel(Base):
    """A single (source-record, attribute) value in long form."""

    __tablename__ = "oil_gas_field_source_values"

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    source_pk: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("oil_gas_field_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    colname: Mapped[str] = mapped_column(String(50), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_num: Mapped[float | None] = mapped_column(PORTABLE_FLOAT, nullable=True)
    value_json: Mapped[Any | None] = mapped_column(PORTABLE_JSON_NULL, nullable=True)

    __table_args__ = (
        # Dense table: at most one value per (record, attribute).
        UniqueConstraint("source_pk", "colname", name="uq_source_value_colname"),
        # Exactly one typed column populated -- a value row is never empty.
        CheckConstraint(
            "(CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_num IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_json IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_source_value_exactly_one",
        ),
        # colname is a closed, code-defined set.
        CheckConstraint(
            "colname IN (" + ", ".join(f"'{n}'" for n in ATTRIBUTE_NAMES) + ")",
            name="ck_source_value_colname",
        ),
        # Empty text is never persisted: NULL/absent is the single "unset"
        # sentinel, so coalescing never has to treat "" as a candidate value.
        # (NULL passes -- the check only rejects the empty string.)
        CheckConstraint(
            "value_text <> ''",
            name="ck_source_value_text_nonempty",
        ),
        # Exact-match + DISTINCT listing across text attributes.
        Index("ix_source_value_colname_text", "colname", "value_text"),
        # Numerically-correct ordered scans (lat/long/years).
        Index("ix_source_value_colname_num", "colname", "value_num"),
    )

    @classmethod
    def from_attribute(cls, colname: str, value: Any) -> OilGasFieldSourceValueModel:
        """Build a value row for ``colname`` routing ``value`` to its column."""
        kind = ATTRIBUTE_KINDS[colname]
        if kind in _NUM_KINDS:
            return cls(colname=colname, value_num=value)
        if kind is ValueKind.JSON:
            return cls(colname=colname, value_json=value)
        return cls(colname=colname, value_text=value)

    def to_attribute(self) -> tuple[str, Any]:
        """Return ``(colname, python_value)`` materialized to its declared type."""
        return self.colname, materialize_value(
            self.colname,
            value_text=self.value_text,
            value_num=self.value_num,
            value_json=self.value_json,
        )

    @classmethod
    def value_col_for(cls, colname: str):
        kind = ATTRIBUTE_KINDS[colname]
        if kind in _NUM_KINDS:
            return cls.value_num
        if kind is ValueKind.JSON:
            return cls.value_json
        return cls.value_text
