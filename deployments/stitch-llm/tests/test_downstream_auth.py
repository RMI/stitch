"""stitch-llm authenticates downstream with its own machine identity.

Suggestions run as detached background jobs, so the caller's token is gone when
the job executes — passthrough is not an option here.
"""

import pytest
from stitch.client.auth import STITCH_CLIENT_BEARER_TOKEN_ENV_VAR
from stitch.service.auth import AuthMode

from stitch.llm import client as client_module


def test_downstream_uses_machine_identity() -> None:
    assert client_module._DOWNSTREAM_AUTH_MODE is AuthMode.machine


def test_validate_downstream_requires_machine_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, raising=False)
    with pytest.raises(ValueError):
        client_module.validate_downstream_auth_config_at_startup()


def test_validate_downstream_passes_with_machine_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "machine-tok")
    client_module.validate_downstream_auth_config_at_startup()
