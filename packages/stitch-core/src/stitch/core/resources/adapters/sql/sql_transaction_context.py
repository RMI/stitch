from sqlalchemy.orm import Session, sessionmaker
from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)
from stitch.core.resources.domain.ports.context import TransactionContext
from stitch.core.resources.domain.ports.sources import SourceRegistryFactory


class SQLTransactionContext(TransactionContext):
    _session_factory: sessionmaker[Session]
    _session: Session | None

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        source_factory: SourceRegistryFactory,
    ):
        self._session_factory = session_factory
        self._session = None
        self._factory = source_factory

    def __enter__(self) -> TransactionContext:
        """Begin transaction"""
        self._session = self._session_factory()
        self.resources = SQLResourceRepository(self._session)
        self.memberships = SQLMembershipRepository(self._session)
        self.source_registry = self._factory(session=self._session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit or rollback based on exception status"""
        try:
            if exc_type is None:
                self.commit()
        except Exception:
            self.rollback()
        finally:
            self._session.close()  # type: ignore[union-attr]

    def commit(self) -> None:
        """Explicitly commit transaction"""
        self._session.commit()

    def rollback(self) -> None:
        """Explicitly rollback transaction"""
        self._session.rollback()
