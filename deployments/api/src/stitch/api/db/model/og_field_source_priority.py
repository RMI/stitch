"""Source priority lookup table for coalescing field values.

The canonical order lives in ``stitch.ogsi.model.SOURCE_PRIORITY``. Production
databases are seeded by the Alembic migrations; the integration tests seed this
table from ``SOURCE_PRIORITY`` in a conftest fixture (they build the schema with
``create_all`` rather than running migrations).
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model import OGSISrcKey

from .common import Base


class OGFieldSourcePriority(Base):
    __tablename__ = "og_field_source_priority"

    source: Mapped[OGSISrcKey] = mapped_column(String(10), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
