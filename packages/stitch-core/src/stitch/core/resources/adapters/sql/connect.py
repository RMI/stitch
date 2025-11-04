from typing import Protocol
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import sessionmaker


class ConnectionConfig(Protocol):
    def to_url(self) -> URL:
        """Creates a `sqlalchem.URL` from configuration properties"""


def Session(config: ConnectionConfig):
    engine = create_engine(config.to_url())
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
