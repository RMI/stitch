from .base import Base, TimestampMixin, UserAuditMixin


class ResourceModel(TimestampMixin, UserAuditMixin, Base): ...
