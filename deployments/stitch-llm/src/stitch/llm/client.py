from __future__ import annotations

from stitch.client import AsyncStitchClient
from stitch.ogsi.model import OGFieldDetailView
from pydantic import ValidationError

from stitch.llm.errors import ModelOutputError
from stitch.llm.settings import Settings, get_settings


class StitchApiClient:
    def __init__(
        self,
        client: AsyncStitchClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or AsyncStitchClient(
            base_url=str(self._settings.api_base_url),
            timeout=30.0,
            use_env_bearer_token=True,
        )

    async def __aenter__(self) -> "StitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_oil_gas_field_detail(self, resource_id: int) -> OGFieldDetailView:
        payload = await self._client.get_oil_gas_field_detail(resource_id)
        try:
            return OGFieldDetailView.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputError(
                "Stitch API returned invalid detail payload."
            ) from exc
