from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: int = Field(...)
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


class Citation(BaseModel):
    url: str
    title: str | None = None


class FieldSuggestionResponse(BaseModel):
    resource_id: int
    field: str
    value: Any
    citations: list[Citation]
    query_succeeded: bool
    model: str
    rationale: str
    observed_at: datetime
    foundry_request: dict[str, Any]
    foundry_response: dict[str, Any]
