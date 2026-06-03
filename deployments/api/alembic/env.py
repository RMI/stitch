from __future__ import annotations

import logging
import os
import time
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import OperationalError

from stitch.api.db.model import StitchBase
from stitch.api.settings import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")
target_metadata = StitchBase.metadata


def get_database_url() -> str:
    return Settings().get_sync_database_url().render_as_string(
        hide_password=False
    )


def wait_for_connection(connectable) -> None:
    timeout_s = int(os.environ.get("STITCH_DB_CONNECT_TIMEOUT_S", "60"))
    interval_s = float(os.environ.get("STITCH_DB_CONNECT_RETRY_INTERVAL_S", "1.0"))
    deadline = time.time() + timeout_s
    last_err: OperationalError | None = None

    while time.time() < deadline:
        try:
            with connectable.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return
        except OperationalError as exc:
            last_err = exc

            logger.info(
                "Database not ready for Alembic yet; retrying in %.1fs",
                interval_s,
            )
            time.sleep(interval_s)

    raise RuntimeError(
        f"DB not reachable within {timeout_s}s for Alembic. Last error: {last_err}"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    external_connection = config.attributes.get("connection")
    if external_connection is not None:
        context.configure(
            connection=external_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()
        return

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    wait_for_connection(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
