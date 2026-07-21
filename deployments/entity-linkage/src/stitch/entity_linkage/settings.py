from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import AnyHttpUrl, Field, SecretStr
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

    # Auth0 M2M (client-credentials) config for calling stitch-api. Optional:
    # when unset the client attaches no Authorization header (local
    # AUTH_DISABLED path). These are surfaced for /health reporting and operator
    # discoverability; the token fetch reads os.environ directly via
    # stitch-client, so they are shared (un-prefixed) STITCH_AUTH_* vars.
    stitch_auth_client_id: str | None = Field(
        default=None, alias="STITCH_AUTH_CLIENT_ID"
    )
    stitch_auth_client_secret: SecretStr | None = Field(
        default=None, alias="STITCH_AUTH_CLIENT_SECRET"
    )
    stitch_auth_audience: str | None = Field(default=None, alias="STITCH_AUTH_AUDIENCE")
    stitch_auth_issuer_url: str | None = Field(
        default=None, alias="STITCH_AUTH_ISSUER_URL"
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def auth_mode(self) -> Literal["m2m", "none"]:
        """Downstream auth mode derived from whether M2M creds are configured."""
        return "m2m" if self.stitch_auth_client_id else "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()
