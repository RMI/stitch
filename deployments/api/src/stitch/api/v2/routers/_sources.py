from fastapi import APIRouter

router = APIRouter(tags=["oil_gas_fields_sources"])


@router.post("/")
def create_source(): ...


@router.get("/")
def query_sources(): ...


@router.get("/{id}")
def get_source_by_id(id: int): ...


@router.put("/{id}")
def replace_source(id: int): ...


@router.patch("/{id}")
def update_source(id: int): ...
