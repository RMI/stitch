#!/usr/bin/env python
"""Fetch every oil & gas field resource to scripts/data/resources.jsonl.

Throwaway demo helper -- not shipped code, not committed.

    uv run scripts/fetch_resources.py

The corpus is small (~9k records, 46 pages at page_size=200), so this always
fetches everything. There is no resume state and no incremental mode: a full
re-fetch takes seconds and is always the cheapest correct thing to do.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

from _common import (
    DATA_DIR,
    RESOURCES_PATH,
    auth_headers,
    base_url,
    flatten_list_item,
)


PAGE_SIZE = 200


def fetch_all() -> tuple[list[dict], int]:
    """Page through the resource list. Returns (records, total_count)."""
    records: list[dict] = []
    total_count = 0
    page = 1

    with httpx.Client(base_url=base_url(), timeout=60.0) as client:
        while True:
            response = client.get(
                "/oil-gas-fields/",
                params={
                    "page": page,
                    "page_size": PAGE_SIZE,
                    "sort_by": "id",
                    "sort_order": "asc",
                },
                headers=auth_headers(),
            )
            response.raise_for_status()
            payload = response.json()

            items = payload.get("items") or []
            records.extend(flatten_list_item(item) for item in items)
            total_count = payload.get("total_count", total_count)
            total_pages = payload.get("total_pages")

            print(
                f"page {page}/{total_pages} -> {len(records)}/{total_count}",
                file=sys.stderr,
            )

            if not items or not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1

    return records, total_count


def main() -> int:
    records, total_count = fetch_all()

    if len(records) != total_count:
        print(
            f"fetched {len(records)} records but API reported {total_count}",
            file=sys.stderr,
        )
        return 1

    ids = [record["id"] for record in records]
    if len(set(ids)) != len(ids):
        print("duplicate resource ids in the fetched pages", file=sys.stderr)
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = RESOURCES_PATH.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp_path, RESOURCES_PATH)

    print(f"wrote {len(records)} records to {RESOURCES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
