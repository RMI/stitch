from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase): ...


class TimestampMixin: ...


class UserAuditMixin: ...
