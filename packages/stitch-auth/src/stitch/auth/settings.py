from pydantic_settings import BaseSettings, SettingsConfigDict


class OIDCSettings(BaseSettings):
    issuer: str
    audience: str
    jwks_uri: str
    algorithms: tuple[str, ...] = ("RS256",)
    jwks_cache_ttl: int = 600
    clock_skew_seconds: int = 30

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
