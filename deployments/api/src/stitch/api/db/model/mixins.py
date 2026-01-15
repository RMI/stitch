from datetime import datetime
from typing import Any, ClassVar, Generic, TypeVar, get_args, get_origin
from pydantic import TypeAdapter
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.ext.hybrid import hybrid_property

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column
from stitch.api.entities import SourceBase
from .types import StitchJson


@declarative_mixin
class TimestampMixin:
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@declarative_mixin
class UserAuditMixin:
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    last_updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


TPayload = TypeVar("TPayload", bound=SourceBase)


def _extract_payload_type(cls: type) -> type | None:
    for base in getattr(cls, "__orig_bases__", []):
        origin = get_origin(base)
        if origin is PayloadMixin:
            args = get_args(base)
            if args:
                return args[0]


@declarative_mixin
class PayloadMixin(Generic[TPayload]):
    __payload_adapter__: ClassVar[TypeAdapter]

    source: Mapped[str] = mapped_column(String, nullable=False)  # "gem" | "woodmac"
    _payload_data: Mapped[dict[str, Any]] = mapped_column(
        "payload", StitchJson(), nullable=False
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        payload_type = _extract_payload_type(cls)
        if payload_type is not None:
            cls.__payload_adapter__ = TypeAdapter(payload_type)

    @hybrid_property
    def payload(self) -> TPayload:
        return self.__payload_adapter__.validate_python(self._payload_data)

    @payload.inplace.setter
    def _payload_setter(self, value: TPayload):
        self.source = value.source
        self._payload_data = value.model_dump(mode="json")

    @payload.inplace.expression  # pyright: ignore[reportArgumentType]
    @classmethod
    def _payload_expression(cls):
        return cls._payload_data
