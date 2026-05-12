from datetime import timedelta
from typing import Any

import jwt
from jwt import PyJWKClient
from pydantic import EmailStr, TypeAdapter, ValidationError

from .claims import TokenClaims
from .errors import JWKSFetchError, TokenExpiredError, TokenValidationError
from .settings import OIDCSettings


_EMAIL = TypeAdapter(EmailStr)


def _extract_permissions(payload: dict[str, Any]) -> frozenset[str]:
    """Extract RBAC permissions from the token payload.

    Auth0-specific: reads the `permissions` array claim. To support another
    IdP, dispatch here off OIDCSettings rather than expanding TokenClaims.
    """
    if "permissions" not in payload or payload["permissions"] is None:
        return frozenset()

    value = payload["permissions"]
    if not isinstance(value, list):
        raise TokenValidationError("permissions claim must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TokenValidationError("permissions claim must be a list of strings")
    return frozenset(value)


def _validated_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return str(_EMAIL.validate_python(candidate))
    except ValidationError:
        return None


class JWTValidator:
    _settings: OIDCSettings
    _jwks_client: PyJWKClient

    def __init__(self, settings: OIDCSettings) -> None:
        self._settings = settings
        self._jwks_client = PyJWKClient(
            uri=settings.jwks_uri,
            cache_jwk_set=True,
            lifespan=settings.jwks_cache_ttl,
        )

    def validate(self, token: str) -> TokenClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except (jwt.PyJWKClientError, jwt.PyJWKClientConnectionError) as e:
            raise JWKSFetchError(str(e)) from e
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(str(e)) from e

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._settings.algorithms),
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                leeway=timedelta(seconds=self._settings.clock_skew_seconds),
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError(str(e)) from e
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(str(e)) from e

        email = _validated_email(payload.get("email"))
        if email is None:
            email = _validated_email(payload.get("preferred_username"))
        name = payload.get("name")
        permissions = _extract_permissions(payload)

        return TokenClaims(
            sub=payload["sub"],
            email=email,
            name=name,
            permissions=permissions,
            raw=payload,
        )
