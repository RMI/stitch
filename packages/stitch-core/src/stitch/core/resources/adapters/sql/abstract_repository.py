from abc import ABC

from sqlalchemy.orm import Session


class AbstractRepository(ABC):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session
