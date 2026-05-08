from __future__ import annotations

import pytest

from stitch.client import StitchAPIError
from stitch.seed import __main__ as seed_main
from stitch.seed.config import SeedConfig


class FakeAsyncStitchClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        use_env_bearer_token: bool = False,
        create_error: Exception | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.use_env_bearer_token = use_env_bearer_token
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


@pytest.mark.anyio
async def test_run_waits_for_health_and_posts_all_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[FakeAsyncStitchClient] = []
    payloads = [
        {"id": None, "source_data": []},
        {"id": 1, "source_data": []},
    ]

    def fake_client_factory(
        base_url: str,
        *,
        timeout: float = 30.0,
        use_env_bearer_token: bool = False,
    ):
        client = FakeAsyncStitchClient(
            base_url,
            timeout=timeout,
            use_env_bearer_token=use_env_bearer_token,
        )
        created_clients.append(client)
        return client

    monkeypatch.setattr(seed_main, "configure_logging", lambda: None)
    monkeypatch.setattr(seed_main, "load_config", make_config)
    monkeypatch.setattr(seed_main, "iter_payloads", lambda **kwargs: payloads)
    monkeypatch.setattr(seed_main, "AsyncStitchClient", fake_client_factory)

    await seed_main.run()

    assert len(created_clients) == 1
    client = created_clients[0]
    assert client.base_url == "http://example.test/api/v1"
    assert client.timeout == 12.5
    assert client.use_env_bearer_token is True
    assert client.wait_calls == [(30, 2.0)]
    assert client.create_calls == payloads
    assert client.closed is True


@pytest.mark.anyio
async def test_run_propagates_shared_client_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[FakeAsyncStitchClient] = []

    def fake_client_factory(
        base_url: str,
        *,
        timeout: float = 30.0,
        use_env_bearer_token: bool = False,
    ):
        client = FakeAsyncStitchClient(
            base_url,
            timeout=timeout,
            use_env_bearer_token=use_env_bearer_token,
            create_error=StitchAPIError("POST /oil-gas-fields/ failed with status 500"),
        )
        created_clients.append(client)
        return client

    monkeypatch.setattr(seed_main, "configure_logging", lambda: None)
    monkeypatch.setattr(seed_main, "load_config", make_config)
    monkeypatch.setattr(
        seed_main,
        "iter_payloads",
        lambda **kwargs: [{"id": None, "source_data": []}],
    )
    monkeypatch.setattr(seed_main, "AsyncStitchClient", fake_client_factory)

    with pytest.raises(StitchAPIError):
        await seed_main.run()

    assert len(created_clients) == 1
    assert created_clients[0].create_calls == [{"id": None, "source_data": []}]
