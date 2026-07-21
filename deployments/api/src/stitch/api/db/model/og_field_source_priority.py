"""Source priority lookup table for coalescing field values."""

from sqlalchemy import Integer, String, event, insert
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model import OGSISrcKey

from .common import Base


class OGFieldSourcePriority(Base):
    __tablename__ = "og_field_source_priority"

    source: Mapped[OGSISrcKey] = mapped_column(String(10), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


DEFAULT_PRIORITIES = [
    {"source": "rmi", "priority": 1},
    {"source": "gem", "priority": 2},
    {"source": "wm", "priority": 3},
    {"source": "ccr", "priority": 4},
    {"source": "llm", "priority": 5},
]


@event.listens_for(OGFieldSourcePriority.__table__, "after_create")
def _seed_priorities(target, connection, **kw):
    for row in DEFAULT_PRIORITIES:
        connection.execute(insert(OGFieldSourcePriority).values(**row))
