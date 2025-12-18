from collections.abc import Generator
from typing import Annotated
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


_engine = create_engine("sqlite://", echo=True)
SessionLocal = sessionmaker(create_engine(""))


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
