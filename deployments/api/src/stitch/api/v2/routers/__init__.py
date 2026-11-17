from ._oil_gas_fields import router as og_field_router
from ._merges import router as og_field_merge_router
from ._sources import router as og_field_source_router

__all__ = ["og_field_source_router", "og_field_merge_router", "og_field_router"]
