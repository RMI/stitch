from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, override

from pydantic import TypeAdapter
from sqlalchemy import (
    JSON,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model import OGFieldSource, OilGasOperator, OilGasOwner
from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    OGSISrcKey,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)

from stitch.api.db.model.types import PORTABLE_BIGINT
from stitch.api.entities import OGFieldQueryParams, User

from .common import Base
from .membership import MembershipModel, MembershipStatus
from .mixins import TimestampMixin, UserAuditMixin
from .og_field_query_mixin import OGFieldQueryMixin


class OilGasFieldSourceModel(OGFieldQueryMixin, TimestampMixin, UserAuditMixin, Base):
    """A single OG field source record (canonicalized), feedable into a Resource."""

    type_adapter: ClassVar[TypeAdapter[OGFieldSource]] = TypeAdapter(OGFieldSource)

    __tablename__: str = "oil_gas_field_sources"

    id: Mapped[int] = mapped_column(PORTABLE_BIGINT, primary_key=True)

    # SqlAlchemy will translate Literal types into Enums
    source: Mapped[OGSISrcKey] = mapped_column(nullable=False)

    # JSON columns
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    operators: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    @classmethod
    @override
    def _base_query(cls, params: OGFieldQueryParams):
        """Filter to sources with at least one active membership."""

        active_membership = (
            select(1)
            .where(MembershipModel.source_pk == cls.id)
            .where(MembershipModel.status == MembershipStatus.ACTIVE)
            .exists()
        )
        stmt = select(cls).where(active_membership)
        for cond in cls._build_conditions(params):
            stmt = stmt.where(cond)
        return cls._apply_sort(stmt, params)

    @classmethod
    def create(
        cls,
        created_by: User,
        source: OGSISrcKey,
        name: str | None = None,
        country: str | None = None,
        basin: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        name_local: str | None = None,
        state_province: str | None = None,
        region: str | None = None,
        reservoir_formation: str | None = None,
        discovery_year: int | None = None,
        production_year_start: int | None = None,
        fid_year: int | None = None,
        location_type: LocationType | None = None,
        production_conventionality: ProductionConventionality | None = None,
        primary_hydrocarbon_group: PrimaryHydrocarbonGroup | None = None,
        field_status: FieldStatus | None = None,
        # None as default to avoid mutable = [] default
        owners: Sequence[OilGasOwner] | None = None,
        operators: Sequence[OilGasOperator] | None = None,
    ):
        return cls(
            source=source,
            name=name,
            country=country,
            basin=basin,
            latitude=latitude,
            longitude=longitude,
            name_local=name_local,
            state_province=state_province,
            region=region,
            reservoir_formation=reservoir_formation,
            discovery_year=discovery_year,
            production_year_start=production_year_start,
            fid_year=fid_year,
            location_type=location_type,
            production_conventionality=production_conventionality,
            primary_hydrocarbon_group=primary_hydrocarbon_group,
            field_status=field_status,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
            owners=[owner.model_dump() for owner in (owners or [])],
            operators=[op.model_dump() for op in (operators or [])],
        )

    @classmethod
    def create_from_entity(cls, ent: OGFieldSource, created_by: User):
        cols = {col.key for col in inspect(cls).columns}
        kwargs = {k: val for k, val in ent.model_dump().items() if k in cols}
        return cls(
            **kwargs, created_by_id=created_by.id, last_updated_by_id=created_by.id
        )

    def as_entity(self) -> OGFieldSource:
        return self.__class__.type_adapter.validate_python(self)

    @classmethod
    def from_entity(cls, entity: OGFieldSource):
        mapper = inspect(cls)
        column_keys = {col.key for col in mapper.columns}
        filtered = {k: v for k, v in entity.model_dump().items() if k in column_keys}
        return cls(**filtered)
