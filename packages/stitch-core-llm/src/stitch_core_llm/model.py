from typing_extensions import TypeForm
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class Citation(BaseModel):
    url: str
    title: str | None = None


class FieldSuggestion(BaseModel):
    resource_id: int
    field: str
    value: Any
    citations: list[Citation]
    model: str
    rationale: str
    observed_at: datetime
    foundry_response: dict[str, Any]


class SuggestedValue[T](BaseModel):
    value: T
    rationale: str
    citations: list[Citation]

    @classmethod
    def model_parametrized_name(cls, params: tuple[TypeForm[Any], ...]) -> str:
        return cls.__name__
