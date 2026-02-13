from typing import Any

from pydantic import BaseModel, Field


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
