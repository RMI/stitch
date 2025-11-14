import logging
import os
from stitch.core.resources.adapters.sql.settings import PostgresConfig
from stitch.core.resources.adapters.sql.model.base import Base
from stitch.core.resources.adapters.sql.model.resource import ResourceModel
from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from stitch.core.resources.adapters.sql.connect import Session
from stitch.core.resources.adapters.sql.sql_resource_repository import (
    SQLResourceRepository,
)
from stitch.core.resources.adapters.sql.sql_membership_repository import (
    SQLMembershipRepository,
)

log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)


def main():
    # Read DB config from environment variables
    config = PostgresConfig()
    logger.debug(f"PostGresConfig: {config}")

    # Create engine and session factory using adapter
    session_factory = Session(config)
    logger.debug(f"Session factory created with config: {config}")

    # Create tables
    logger.debug("Creating tables...")
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    logger.debug("Tables created.")

    # Create a session
    session = session_factory()

    try:
        # Create Resource
        resource_repo = SQLResourceRepository(session)
        logger.debug("Creating Resource...")
        resource_id = resource_repo.create(
            name="Test Resource",
            country="USA",
            latitude=37.7749,
            longitude=-122.4194,
            created_by="seed_script",
        )
        logger.debug(f"Resource created: {resource_id}")

        # Create Membership
        membership_repo = SQLMembershipRepository(session)
        logger.debug("Creating Membership...")
        membership_id = membership_repo.create(
            resource_id=resource_id,
            source="gem",
            source_pk="123",
        )
        logger.debug(f"Membership created: {membership_id}")

        # Commit all changes
        session.commit()
        logger.debug("Committed all changes to the database.")

        # Debug: Print all resources
        resources = session.query(ResourceModel).all()
        for r in resources:
            logger.debug(f"Resource: {r.id}, {r.name}")

        logger.debug(f"Resources in DB: {resources}")

        memberships = session.query(MembershipModel).all()
        logger.debug(f"Memberships in DB: {memberships}")

    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
