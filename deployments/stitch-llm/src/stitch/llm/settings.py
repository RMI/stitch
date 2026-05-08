from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "STITCH_LLM_LOG_LEVEL"),
    )
    frontend_origin_url: AnyHttpUrl = Field(
        default="http://localhost:3000",
        alias="STITCH_LLM_FRONTEND_ORIGIN_URL",
    )
    auth_disabled: bool = Field(default=False, alias="AUTH_DISABLED")

    api_base_url: AnyHttpUrl = Field(
        default="http://api:8000/api/v1",
        alias="STITCH_LLM_API_BASE_URL",
    )
    auth_mode: Literal["env_bearer_token"] = Field(
        default="env_bearer_token",
        alias="STITCH_LLM_AUTH_MODE",
    )

    azure_openai_base_url: AnyHttpUrl | None = Field(
        default=None,
        alias="STITCH_LLM_AZURE_OPENAI_BASE_URL",
        description="Azure OpenAI v1 base URL, for example https://<resource>.openai.azure.com/openai/v1",
    )
    azure_openai_api_key: SecretStr | None = Field(
        default=None,
        alias="STITCH_LLM_AZURE_OPENAI_API_KEY",
    )
    azure_openai_model: str | None = Field(
        default=None,
        alias="STITCH_LLM_AZURE_OPENAI_MODEL",
    )
    azure_openai_timeout_seconds: float = Field(
        default=30.0,
        alias="STITCH_LLM_AZURE_OPENAI_TIMEOUT_SECONDS",
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "azure_openai_base_url",
        "azure_openai_api_key",
        "azure_openai_model",
        mode="before",
    )
    @classmethod
    def empty_strings_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def azure_openai_configured(self) -> bool:
        return all(
            (
                self.azure_openai_base_url is not None,
                self.azure_openai_api_key is not None,
                self.azure_openai_model,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
