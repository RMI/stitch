from pathlib import Path
from typing import ClassVar, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

Dialect = Literal["postgresql", "sqlite"]


class PostgresConfig(BaseSettings, cli_parse_args=False):
    """PostgreSQL configuration that reads from env vars (PG_*) or .env file.

    Priority: Environment variables > .env file > defaults

    Note: TOML configuration is not supported for PostgreSQL to avoid
    security concerns. Use environment variables or .env file instead.
    """

    host: str = "xxx"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = "xxx"

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="PG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def to_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            database=self.database,
            port=self.port,
        )


class SqliteConfig(BaseSettings):
    db_path: Path

    def to_url(self) -> URL:
        return URL.create(drivername="sqlite", database=str(self.db_path))
