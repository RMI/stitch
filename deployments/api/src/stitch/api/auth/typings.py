from typing import Any, Protocol

from fastapi import Request
from pydantic import BaseModel, Field

from stitch.api.entities import User


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    permissions: frozenset[str] = Field(default_factory=frozenset)
    raw: dict[str, Any] = Field(default_factory=dict)


class AuthenticatedUser(User):
    claims: TokenClaims


class AuthProvider(Protocol):
    async def authenticate(self, request: Request) -> TokenClaims: ...
