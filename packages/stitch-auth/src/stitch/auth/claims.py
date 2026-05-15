from typing import Any

from pydantic import BaseModel, Field


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    permissions: frozenset[str] = Field(default_factory=frozenset)
    raw: dict[str, Any] = Field(default_factory=dict)
