from pydantic import BaseModel, Field


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    raw: dict = Field(default_factory=dict)
