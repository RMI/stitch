class AuthError(Exception):
    """Base for all auth errors. Consumers can catch broadly or narrowly."""


class TokenExpiredError(AuthError): ...


class TokenValidationError(AuthError): ...


class JWKSFetchError(AuthError): ...
