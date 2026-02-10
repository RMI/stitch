from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OIDCSettings(BaseSettings):
    issuer: str = ""
    audience: str = ""
    jwks_uri: str = ""
    algorithms: tuple[str, ...] = ("RS256",)
    jwks_cache_ttl: int = 600
    clock_skew_seconds: int = 30
    disabled: bool = False

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _require_fields_when_enabled(self) -> Self:
        if not self.disabled:
            missing = [
                f for f in ("issuer", "audience", "jwks_uri") if not getattr(self, f)
            ]
            if missing:
                raise ValueError(f"Required when AUTH_DISABLED is not true: {missing}")
        return self
