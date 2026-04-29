from typing import Any

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: int = Field(...)
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


class FieldSuggestionResponse(BaseModel):
    resource_id: int
    field: str
    value: Any
    model: str
    foundry_request: dict[str, Any]
    foundry_response: dict[str, Any]
