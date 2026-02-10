from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .common import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("sub", name="uq_users_sub"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sub: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str]
    email: Mapped[str]
