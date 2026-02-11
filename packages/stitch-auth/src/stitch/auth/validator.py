from datetime import timedelta

import jwt
from jwt import PyJWKClient

from .claims import TokenClaims
from .errors import JWKSFetchError, TokenExpiredError, TokenValidationError
from .settings import OIDCSettings


class JWTValidator:
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
                    "require": ["exp", "iss", "aud", "sub", "nbf"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError(str(e)) from e
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(str(e)) from e

        email = payload.get("email") or payload.get("preferred_username")
        name = payload.get("name")

        return TokenClaims(
            sub=payload["sub"],
            email=email,
            name=name,
            raw=payload,
        )
