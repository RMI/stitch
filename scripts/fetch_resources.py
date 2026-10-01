#!/usr/bin/env python
"""Snapshot the resource list to scripts/data/resources.jsonl for the matcher.

    ./scripts/fetch_resources.py                     # local docker postgres
    ./scripts/fetch_resources.py --db-host 1.2.3.4   # a specific host
    ./scripts/fetch_resources.py --db-url postgresql+psycopg://...

Reads the precomputed current-state read model (`og_field_resource_state`), which
already holds every field coalesced plus a `provenance` map of field -> winning
source. Earlier versions recomputed that pivot here in hand-inlined SQL; that
copy of the coalescing logic silently broke when `og_field_source_priority` and
`og_field_resource_source_priority` were collapsed into
`og_field_resource_attribute_priority`, so the read model is now the single
source of truth. It is rebuildable at any time with
`python -m stitch.api.db.read_model.rebuild`.

Licensing is unrestricted, as before: the mask selected is the one where every
source is visible, because a licence-filtered corpus would hide duplicate
candidates.

Output rows keep the shape `find_candidates.py` expects. Connection settings and
their precedence are documented in `lib.settings`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.read_model.permissions import ALL_SOURCES, mask_for_sources

from lib._common import DATA_DIR, RESOURCES_PATH, distinct_sources, open_session
from lib.settings import script_settings

# Every source visible: the unrestricted corpus the matcher needs.
UNRESTRICTED_MASK = mask_for_sources(ALL_SOURCES)

# Stored as JSON lists of {"name": ..., "stake": ...}; the matcher wants names.
JSON_FIELDS = ("operators", "owners")

# The fields `flatten_list_item` projects, in ITS key order: json.dumps emits
# keys in insertion order and the output is diffed against earlier runs.
FIELD_ORDER = (
    "name",
    "country",
    "latitude",
    "longitude",
    "name_local",
    "state_province",
    "region",
    "basin",
    "operators",
    "owners",
    "field_status",
)

SNAPSHOT_SQL = text(f"""
    SELECT resource_id, {", ".join(FIELD_ORDER)}, provenance
    FROM og_field_resource_state
    WHERE permission_mask = :mask
    ORDER BY resource_id
""")


async def write_snapshot(session: AsyncSession, mask: int) -> int:
    """Stream the coalesced rows out to JSONL, one record per resource id."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    with RESOURCES_PATH.open("w", encoding="utf-8") as handle:
        result = await session.stream(SNAPSHOT_SQL, {"mask": mask})

        async for row in result.mappings():
            record: dict = {"id": row["resource_id"]}
            for field in FIELD_ORDER:
                value = row[field]
                if field in JSON_FIELDS:
                    # NULL means no winner for the field: an empty list, as the
                    # previous implementation emitted.
                    record[field] = [entry["name"] for entry in value or []]
                else:
                    record[field] = value
            record["sources"] = distinct_sources(row["provenance"])

            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot the resource list for the matcher.",
        epilog="Without any option, targets the local docker postgres.",
    )
    parser.add_argument(
        "--db-url",
        help="whole SQLAlchemy URL; overrides every other target option",
    )
    parser.add_argument(
        "--db-host",
        help="hostname, or a shorthand: local, staging (see lib.settings)",
    )
    parser.add_argument("--db-port", type=int, help="database port")
    parser.add_argument("--db-name", help="database name")
    parser.add_argument("--db-user", help="database user")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    url = script_settings().database_url(
        url=args.db_url,
        host=args.db_host,
        port=args.db_port,
        database=args.db_name,
        user=args.db_user,
    )

    async with open_session(url) as session:
        written = await write_snapshot(session, UNRESTRICTED_MASK)

    print(f"wrote {written} records to {RESOURCES_PATH}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
