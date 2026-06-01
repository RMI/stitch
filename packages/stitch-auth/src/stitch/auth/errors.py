from collections.abc import Iterable


class AuthError(Exception):
    """Base for all auth errors. Consumers can catch broadly or narrowly."""


class TokenExpiredError(AuthError): ...


class TokenValidationError(AuthError): ...


class JWKSFetchError(AuthError): ...


class InsufficientPermissionsError(AuthError):
    detail: str
    granted: frozenset[str]
    required: frozenset[str]
    missing: frozenset[str]

    def __init__(
        self,
        granted: Iterable[str],
        required: Iterable[str],
        missing: Iterable[str] | None = None,
        detail: str | None = None,
    ):
        self.granted = frozenset(granted)
        self.required = frozenset(required)
        self.missing = (
            frozenset(missing)
            if missing is not None
            else self.required.difference(self.granted)
        )
        self.detail = detail or _permission_detail(self.missing)
        super().__init__(self.detail)


def _permission_detail(missing: Iterable[str]) -> str:
    missing_text = ", ".join(sorted(missing))
    if not missing_text:
        return "Missing required permission(s)"
    return f"Missing required permission(s): {missing_text}"
