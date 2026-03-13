from collections.abc import Sequence
from functools import reduce
from typing import Any
from stitch.ogsi.model import (
    GEM_SRC,
    LLM_SRC,
    RMI_SRC,
    WM_SRC,
    OGFieldSource,
)
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

SRC_PRIORITY = (RMI_SRC, WM_SRC, GEM_SRC, LLM_SRC)


type ProvAttrs = dict[str, tuple[Any, OGSISrcKey, int] | None]


def coalesce_og_field_resource(
    source_data: Sequence[OGFieldSource],
) -> tuple[OilGasFieldBase, ProvAttrs]:
    """
    Coalesce all source payloads into a single `OGFieldView`.

    Placeholder logic (shape-first):
        - in `source_data` order, fill any still-missing fields with the
        first non-null value found
    """

    def _reducer(acc: ProvAttrs, src: OGFieldSource) -> ProvAttrs:
        # get non-None values from src excluding `id` and `source`
        # matches the OilGasFieldBase structure
        update_: ProvAttrs = {
            key: (up_val, src.source, src.id)
            for key, up_val in src.model_dump(
                exclude={"id", "source"}, exclude_none=True
            ).items()
            # account for optional id, shouldn't happen but here for type hints
            if src.id is not None
        }
        return {**acc, **update_}

    # sort in  reverse priority order so latter models override
    ordered_sources = sorted(
        source_data,
        reverse=True,
        key=lambda src: SRC_PRIORITY.index(src.source),
    )

    provenanced_attrs = reduce(
        _reducer,
        ordered_sources,
        {key: None for key in OilGasFieldBase.model_fields.keys()},
    )

    final_attrs = {
        key: val[0] if val is not None else None
        for key, val in provenanced_attrs.items()
    }
    return OilGasFieldBase(**final_attrs), provenanced_attrs
