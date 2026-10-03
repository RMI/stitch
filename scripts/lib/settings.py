"""Settings for the scripts, layered over the repo env files."""

from __future__ import annotations

import os
from functools import cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

from stitch.api.settings import PostgresConfig

from .env import load_script_env

DB_HOST_ALIASES = {
    "local": "localhost",
    "db": "localhost",
    "staging": "stitch-staging.postgres.database.azure.com",
}
HOST_ALIAS_PREFIX = "SCRIPTS_HOST_"

EXTRA_PREFIX = "SCRIPTS__"


def _extras() -> dict[str, str]:
    """Every ``SCRIPTS__<NAME>`` in the environment, keyed by lowercased name."""
    return {
        key.removeprefix(EXTRA_PREFIX).lower(): value
        for key, value in os.environ.items()
        if key.startswith(EXTRA_PREFIX) and key != EXTRA_PREFIX
    }


def resolve_host(host: str | None) -> str | None:
    """Expand a shorthand like ``staging``; pass any other value through."""
    if not host:
        return host
    return os.environ.get(
        f"{HOST_ALIAS_PREFIX}{host.upper()}",
        DB_HOST_ALIASES.get(host, host),
    )


class ScriptSettings(BaseSettings):
    """How the scripts reach Postgres, local or deployed."""

    db: PostgresConfig = Field(default_factory=PostgresConfig)

    db_url: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None

    extras: dict[str, str] = Field(default_factory=_extras)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="SCRIPTS_",
        extra="ignore",
    )

    def database_url(
        self,
        *,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
    ) -> URL:
        """The URL to connect to, with caller overrides winning over the env."""
        whole = url or self.db_url
        if whole:
            return make_url(whole)

        base = self.db.to_url()

        return base.set(
            host=resolve_host(host or self.db_host or base.host),
            port=port or self.db_port or base.port,
            database=database or self.db_name or base.database,
            username=user or self.db_user or base.username,
        )


@cache
def script_settings() -> ScriptSettings:
    """The settings for this process, with the env files loaded first."""
    load_script_env()
    return ScriptSettings()
