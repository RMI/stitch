from stitch.ogsi.model.og_field import OilGasFieldBase
from collections.abc import MutableMapping
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter(tags=["oil-gas-fields"])


class OilGasFieldSourceV2(BaseModel):
    id: int
    data: OilGasFieldBase


class OilGasFieldRequestV2(BaseModel):
    attribute_priorities: MutableMapping[str, tuple[int, str]]
    sources: list[OilGasFieldSourceV2]


@router.post("/")
def create_resource(): ...


@router.get("/")
def query_resources():
    return []


@router.get("/{id}")
def get_resource_by_id(id: int): ...


@router.get("/{id}/suggest")
def get_attribute_suggestions(id: int): ...


@router.put("/{id}")
def replace_resource(id: int, resource_in: OilGasFieldRequestV2):
    """Make a complete, idempotent replacement for the resource data passed in the body.


    - handle `attribute_priorities` dict
    - handle `sources` list

    Args:
        id:
        resource_in:
    """
    ...


@router.patch("/{id}")
def update_resource(id: int): ...
