from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine
from stitch.api.settings import Settings as ApiSettings

logger = logging.getLogger("stitch.api.alembic")
ADVISORY_LOCK_NAME = "stitch_alembic_migrate"


@dataclass(frozen=True)
class Settings:
    database_url: str
    alembic_config_path: str
    connect_timeout_s: int
    connect_retry_interval_s: float
    revision: str = "head"
    use_advisory_lock: bool = True


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value


def build_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return ApiSettings().get_sync_database_url().render_as_string(hide_password=False)


def default_alembic_config_path() -> str:
    return str(Path(__file__).resolve().parents[3] / "alembic.ini")


def load_settings(revision: str = "head") -> Settings:
    use_advisory_lock = _env("STITCH_DB_USE_ADVISORY_LOCK", "true").lower()
    return Settings(
        database_url=build_db_url(),
        alembic_config_path=_env(
            "STITCH_ALEMBIC_CONFIG", default_alembic_config_path()
        ),
        connect_timeout_s=int(_env("STITCH_DB_CONNECT_TIMEOUT_S", "60")),
        connect_retry_interval_s=float(
            _env("STITCH_DB_CONNECT_RETRY_INTERVAL_S", "1.0")
        ),
        revision=revision,
        use_advisory_lock=use_advisory_lock not in {"0", "false", "no"},
    )


def wait_for_db(engine: Engine, timeout_s: int, interval_s: float) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_err = exc
            time.sleep(interval_s)
    raise RuntimeError(f"DB not reachable within {timeout_s}s. Last error: {last_err}")


def acquire_lock(conn) -> None:
    conn.execute(text(f"SELECT pg_advisory_lock(hashtext('{ADVISORY_LOCK_NAME}'), 0)"))


def release_lock(conn) -> None:
    try:
        conn.execute(
            text(f"SELECT pg_advisory_unlock(hashtext('{ADVISORY_LOCK_NAME}'), 0)")
        )
    except Exception:
        logger.exception("ERROR releasing advisory lock")


def build_alembic_config(settings: Settings) -> Config:
    return Config(settings.alembic_config_path)


def _run_with_connection(
    *,
    operation_name: str,
    revision: str = "head",
    runner,
) -> None:
    setup_logging()
    settings = load_settings(revision=revision)
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    logger.info("waiting for DB...")
    wait_for_db(
        engine,
        timeout_s=settings.connect_timeout_s,
        interval_s=settings.connect_retry_interval_s,
    )

    logger.info("running alembic %s...", operation_name)
    with engine.begin() as conn:
        try:
            if settings.use_advisory_lock:
                logger.info("acquiring advisory lock...")
                acquire_lock(conn)

            config = build_alembic_config(settings)
            config.attributes["connection"] = conn
            runner(config, settings)
            logger.info("alembic %s complete.", operation_name)
        finally:
            if settings.use_advisory_lock:
                logger.info("releasing advisory lock...")
                release_lock(conn)

    engine.dispose()


def run_upgrade(revision: str = "head") -> None:
    def _upgrade(config: Config, settings: Settings) -> None:
        command.upgrade(config, settings.revision)

    _run_with_connection(
        operation_name=f"upgrade to {revision}",
        revision=revision,
        runner=_upgrade,
    )


def run_autogenerate(message: str = "baseline") -> None:
    def _autogenerate(config: Config, settings: Settings) -> None:
        command.revision(config, message=message, autogenerate=True)

    _run_with_connection(
        operation_name=f'autogenerate revision "{message}"',
        runner=_autogenerate,
    )
