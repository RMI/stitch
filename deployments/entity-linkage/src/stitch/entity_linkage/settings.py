from functools import lru_cache
from typing import ClassVar

from pydantic import AnyHttpUrl, Field
from pydantic_settings import SettingsConfigDict
from stitch.observability import OTelSettings


class Settings(OTelSettings):
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

    # How long to wait on a single downstream request, and how many times to
    # retry one that fails in transit. A linkage pass makes a very large number
    # of requests, so the odds of hitting at least one transient failure are
    # high; retrying keeps a whole pass from being lost to a single blip.
    api_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        alias="ENTITY_LINKAGE_API_TIMEOUT_SECONDS",
    )
    api_max_retries: int = Field(
        default=2,
        ge=0,
        alias="ENTITY_LINKAGE_API_MAX_RETRIES",
    )

    # NB: no env_prefix here. The OTEL_* fields inherited from OTelSettings
    # resolve by their bare env names (OTEL_TRACES_EXPORTER, ...); a prefix would
    # silently stop them — and the test suite's OTEL_TRACES_EXPORTER=none guard —
    # from being read. Scope any future prefix to individual fields instead.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
