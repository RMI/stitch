from __future__ import annotations

import pytest

from stitch.client import StitchAPIError
from stitch.seed import __main__ as seed_main
from stitch.seed.config import SeedConfig


class FakeAsyncStitchClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        timeout: float = 30.0,
        create_error: Exception | None = None,
    ) -> None:
        self.api_base_url = api_base_url
        self.timeout = timeout
        self.create_error = create_error
        self.wait_calls: list[tuple[int, float]] = []
        self.create_calls: list[dict] = []
        self.closed = False

    async def __aenter__(self) -> "FakeAsyncStitchClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    async def wait_for_health(self, retries: int = 30, delay: float = 2.0) -> None:
        self.wait_calls.append((retries, delay))

    async def create_oil_gas_field(self, payload: dict) -> dict:
        self.create_calls.append(payload)
        if self.create_error is not None:
            raise self.create_error
        return {"id": len(self.create_calls)}


def make_config() -> SeedConfig:
    return SeedConfig(
        api_base_url="http://example.test/api/v1",
        faker_post_count=2,
        http_timeout_seconds=12.5,
        static_payload_dir=None,
        random_seed=7,
        seed_source="mixed",
        null_probability=0.1,
    )


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    created: list[FakeAsyncStitchClient],
    *,
    create_error: Exception | None = None,
) -> list[dict]:
    """Patch seed __main__ to record the built client and the auth validator.

    Seed now builds its client via ``AsyncStitchClient.from_service_env`` (auth
    mode selected by the environment) and awaits the shared
    ``validate_downstream_auth_at_startup`` before connecting.
    """
    validate_calls: list[dict] = []

    async def fake_validate(*, api_base_url: str) -> None:
        validate_calls.append({"api_base_url": api_base_url})

    class FakeClientFactory:
        @classmethod
        def from_service_env(
            cls, *, api_base_url: str, timeout: float = 30.0
        ) -> FakeAsyncStitchClient:
            client = FakeAsyncStitchClient(
                api_base_url=api_base_url,
                timeout=timeout,
                create_error=create_error,
            )
            created.append(client)
            return client

    monkeypatch.setattr(seed_main, "configure_logging", lambda: None)
    monkeypatch.setattr(seed_main, "load_config", make_config)
    monkeypatch.setattr(seed_main, "AsyncStitchClient", FakeClientFactory)
    monkeypatch.setattr(seed_main, "validate_downstream_auth_at_startup", fake_validate)
    return validate_calls


@pytest.mark.anyio
async def test_run_waits_for_health_and_posts_all_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeAsyncStitchClient] = []
    validate_calls = _install_fakes(monkeypatch, created)
    payloads = [
        {"id": None, "source_data": []},
        {"id": 1, "source_data": []},
    ]
    monkeypatch.setattr(seed_main, "iter_payloads", lambda **kwargs: payloads)

    await seed_main.run()

    # Startup validator ran first, against the configured base URL.
    assert validate_calls == [{"api_base_url": "http://example.test/api/v1"}]

    assert len(created) == 1
    client = created[0]
    assert client.api_base_url == "http://example.test/api/v1"
    assert client.timeout == 12.5
    assert client.wait_calls == [(30, 2.0)]
    assert client.create_calls == payloads
    assert client.closed is True


@pytest.mark.anyio
async def test_run_propagates_shared_client_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeAsyncStitchClient] = []
    _install_fakes(
        monkeypatch,
        created,
        create_error=StitchAPIError("POST /oil-gas-fields/ failed with status 500"),
    )
    monkeypatch.setattr(
        seed_main,
        "iter_payloads",
        lambda **kwargs: [{"id": None, "source_data": []}],
    )

    with pytest.raises(StitchAPIError):
        await seed_main.run()

    assert len(created) == 1
    assert created[0].create_calls == [{"id": None, "source_data": []}]
