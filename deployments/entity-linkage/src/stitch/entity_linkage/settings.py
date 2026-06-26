from functools import lru_cache
from typing import ClassVar

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    log_level: str = Field(default="INFO", alias="ENTITY_LINKAGE_LOG_LEVEL")
    frontend_origin_url: AnyHttpUrl = Field(
        default="http://localhost:3000",
        alias="ENTITY_LINKAGE_FRONTEND_ORIGIN_URL",
    )
    auth_disabled: bool = Field(default=False, alias="AUTH_DISABLED")

    # explicit downstream API target
    api_base_url: AnyHttpUrl = Field(
        default="http://api:8000/api/v1",
        alias="ENTITY_LINKAGE_API_BASE_URL",
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
