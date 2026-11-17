from fastapi import APIRouter

router = APIRouter(tags=["oil_gas_fields_merges"])


@router.post("/")
def create_merge(): ...


@router.get("/")
def query_merges(): ...


@router.get("/")
def get_merge_score(): ...


@router.get("/suggest")
def get_merge_suggestions(): ...


@router.get("/{id}")
def get_merge_by_id(id: int): ...


@router.put("/{id}")
def replace_merge(id: int): ...


@router.patch("/{id}")
def update_merge(id: int): ...
