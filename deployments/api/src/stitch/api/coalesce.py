from collections.abc import Mapping, Sequence
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

SRC_PRIORITY = (RMI_SRC, GEM_SRC, WM_SRC, LLM_SRC)


type ProvAttrs = dict[str, tuple[Any, OGSISrcKey, int] | None]

# field -> {source record id (source_pk) -> raw override priority}. A record with
# an entry here is pinned for that field; the tier logic below always ranks it
# above non-overridden records for that field.
type FieldOverrides = Mapping[str, Mapping[int, int]]

# (tier, effective_priority, default_priority, source_key, source_id): a total
# order per field. tier 0 = pinned by an override, tier 1 = not. Lower wins.
type _SortKey = tuple[int, int, int, OGSISrcKey, int]


def coalesce_og_field_resource(
    source_data: Sequence[OGFieldSource],
    priorities: Sequence[OGSISrcKey] = SRC_PRIORITY,
    *,
    field_overrides: FieldOverrides | None = None,
) -> tuple[OilGasFieldBase, ProvAttrs]:
    """Coalesce all source payloads into a single ``OGFieldView``.

    For each field independently, pick the source record with the smallest sort
    key among records carrying a value for that field. The sort key
    places any record pinned by a ``field_overrides`` entry (tier 0, ordered by
    the override priority) ahead of every non-pinned record (tier 1, ordered by
    the source's global default priority). So a source added *after* a curator
    reordered a field -- which has no override row -- always sorts last for that
    field, regardless of its default priority.

    With ``field_overrides`` empty/``None`` this reduces to the pre-override
    behaviour: every record is tier 1, ordered by ``priorities`` then id.
    """
    prio_index = {src_key: i for i, src_key in enumerate(priorities)}
    overrides = field_overrides or {}
    # Tier-1 fallback rank for a source absent from ``priorities`` (shouldn't
    # happen): sort after all known sources rather than raise.
    _unknown = len(prio_index)

    def default_prio(src: OGFieldSource) -> int:
        return prio_index.get(src.source, _unknown)

    def sort_key(field: str, src: OGFieldSource, src_id: int) -> _SortKey:
        override = overrides.get(field, {}).get(src_id)
        base = default_prio(src)
        if override is not None:
            return (0, override, base, src.source, src_id)
        return (1, base, base, src.source, src_id)

    provenanced: ProvAttrs = {key: None for key in OilGasFieldBase.model_fields}
    for field in provenanced:
        best: tuple[_SortKey, Any, OGSISrcKey, int] | None = None
        for src in source_data:
            if src.id is None:
                continue
            value = getattr(src, field)
            # Skip absent values. Empty text is never persisted (the write path
            # drops it and the DB's ck_source_value_text_nonempty CHECK enforces
            # it), so NULL/absent is the single "unset" sentinel here.
            if value is None:
                continue
            key = sort_key(field, src, src.id)
            if best is None or key < best[0]:
                best = (key, value, src.source, src.id)
        if best is not None:
            _, value, source_key, source_id = best
            provenanced[field] = (value, source_key, source_id)

    final_attrs = {
        key: val[0] if val is not None else None for key, val in provenanced.items()
    }
    return OilGasFieldBase(**final_attrs), provenanced
