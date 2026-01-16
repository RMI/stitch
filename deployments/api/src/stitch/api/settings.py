from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

Dialect = Literal["postgresql", "sqlite"]


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class PostgresConfig(BaseSettings, cli_parse_args=False):
    host: str = "localhost"
    port: int = 5432
    db: str = "postgres"
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def to_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            database=self.db,
            port=self.port,
        )


class SqliteConfig(BaseSettings):
    db_path: Path | None = None

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="SQLITE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def to_url(self) -> URL:
        db = str(self.db_path) if self.db_path is not None else ":memory:"
        return URL.create(drivername="sqlite+aiosqlite", database=db)


class Settings(BaseSettings):
    environment: Environment = Environment.DEV
    dialect: Dialect = "postgresql"

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_database_url(self) -> URL:
        if self.dialect == "sqlite":
            return SqliteConfig().to_url()
        return PostgresConfig().to_url()


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, get_settings]
