#! /usr/bin/env -S uv run --package stitch-api --exact

"""CLI benchmark: old query() vs new query_v2() on a large SQLite database.

Core logic is split into importable functions (build_db / build_matrix / compare_all)
for clarity. This is a developer tool; it is never imported by application code.

By default only the new query_v2() is timed (the point is confirming the new path
is fast). Pass --compare-old to also run the old query() and assert identical
results — a correctness cross-check, but slow at scale.

Usage:
    ./scripts/test_query.py run [--rows N] [--keep] [--compare-old] [--profile]
"""

from __future__ import annotations

import asyncio
import cProfile
import io
import pstats
import random
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# SQLite version guard (window functions + NULLS LAST need >= 3.30)
# ---------------------------------------------------------------------------

if sqlite3.sqlite_version_info < (3, 30, 0):
    click.echo(
        f"ERROR: SQLite >= 3.30.0 required (window functions / NULLS LAST).\n"
        f"       Found: {sqlite3.sqlite_version}",
        err=True,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Stitch imports (after guard so bad environments fail fast)
# ---------------------------------------------------------------------------

from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
    StitchBase,
    UserModel,
)
from stitch.api.db.og_field_query_view_refresh import rebuild_all
from stitch.api.db import og_field_resource_actions as _old
from stitch.api.db import og_field_query_view_actions as _new
from stitch.api.entities import OGFieldQueryParams

# ---------------------------------------------------------------------------
# Fixed seed for reproducibility
# ---------------------------------------------------------------------------

_RNG = random.Random(42)

_SOURCES = ["rmi", "wm", "gem", "llm"]
_COUNTRIES = ["USA", "CAN", "MEX", "BRA", "NOR", "GBR", "NGA", "AGO"]
_NAMES_WITH_PERM = [
    "Permian Basin Alpha",
    "Permian Basin Beta",
    "Permian Deep",
    "Superfield Perm",
]
_NAME_POOL = [
    "Eagle Ford",
    "Bakken",
    "Marcellus",
    "Haynesville",
    "Wolfcamp",
    "Spraberry",
    "Bone Spring",
    "Niobrara",
    "Montney",
    "Duvernay",
    "Cardium",
    "Viking",
    "Brent",
    "Forties",
    "Statfjord",
    "Ekofisk",
    "Troll",
    "Oseberg",
    "Snorre",
    "Heidrun",
    "Agbami",
    "Bonga",
    "Erha",
    "Forcados",
    "Girassol",
    "Dalia",
    "Rosa",
    "Block 31",
    "Jubilee",
    "Tullow",
]


def _rand_name() -> str | None:
    """Return a name; ~15 % contain 'perm', ~10 % are None."""
    r = _RNG.random()
    if r < 0.10:
        return None
    if r < 0.25:
        return _RNG.choice(_NAMES_WITH_PERM)
    return _RNG.choice(_NAME_POOL)


def _rand_year() -> int | None:
    if _RNG.random() < 0.12:
        return None
    return _RNG.randint(1950, 2020)


def _rand_country() -> str | None:
    if _RNG.random() < 0.08:
        return None
    return _RNG.choice(_COUNTRIES)


_NOW_ISO = datetime.now(timezone.utc).isoformat()
_SOURCE_RECORD_BASE = {"observed_at": _NOW_ISO, "producer": "stress-script"}


# ---------------------------------------------------------------------------
# Core importable functions
# ---------------------------------------------------------------------------


async def build_db(
    rows: int = 80_000,
    url: str | None = None,
    *,
    file_path: str | None = None,
) -> tuple[Any, AsyncSession]:
    """Build an in-memory or on-disk SQLite DB seeded with *rows* rows.

    Returns ``(engine, session)``; caller is responsible for closing both.
    The session has an open transaction — call ``await session.flush()`` before
    querying if you need the data visible.

    Parameters
    ----------
    rows:       number of sources AND resources to create (each resource gets
                1–3 memberships, so memberships > rows).
    url:        full SQLAlchemy async URL, e.g. ``"sqlite+aiosqlite:///:memory:"``.
                If None, *file_path* is used (on-disk).
    file_path:  path for the on-disk SQLite file when *url* is None.
    """
    if url is None:
        if file_path is None:
            raise ValueError("Provide url or file_path")
        url = f"sqlite+aiosqlite:///{file_path}"

    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(StitchBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()

    # ---- user (FK anchor) --------------------------------------------------
    user_row = UserModel(id=1, sub="stress|script", name="Stress Script", email=None)
    session.add(user_row)
    await session.flush()

    user_id = 1

    # ---- sources -----------------------------------------------------------
    chunk = 2_000
    source_ids: list[int] = []
    source_key_by_id: dict[int, str] = {}

    total_sources = rows
    inserted = 0
    sid = 1
    while inserted < total_sources:
        batch_size = min(chunk, total_sources - inserted)
        batch = []
        for _ in range(batch_size):
            src_key = _RNG.choice(_SOURCES)
            batch.append(
                {
                    "id": sid,
                    "source": src_key,
                    "name": _rand_name(),
                    "country": _rand_country(),
                    "name_local": None,
                    "state_province": None,
                    "region": None,
                    "basin": None,
                    "reservoir_formation": None,
                    "latitude": None,
                    "longitude": None,
                    "discovery_year": _rand_year(),
                    "production_start_year": _rand_year(),
                    "fid_year": _rand_year(),
                    "location_type": None,
                    "production_conventionality": None,
                    "primary_hydrocarbon_group": None,
                    "field_status": None,
                    "owners": None,
                    "operators": None,
                    "source_record": {
                        **_SOURCE_RECORD_BASE,
                        "payload": {"source": src_key},
                    },
                    "created_by_id": user_id,
                    "last_updated_by_id": user_id,
                }
            )
            source_key_by_id[sid] = src_key
            source_ids.append(sid)
            sid += 1
        await session.execute(insert(OilGasFieldSourceModel), batch)
        inserted += batch_size

    # ---- resources ---------------------------------------------------------
    total_resources = rows
    resource_ids: list[int] = []
    rid = 1
    inserted = 0
    while inserted < total_resources:
        batch_size = min(chunk, total_resources - inserted)
        batch = []
        for _ in range(batch_size):
            batch.append(
                {
                    "id": rid,
                    "repointed_id": None,
                    "created_by_id": user_id,
                    "last_updated_by_id": user_id,
                }
            )
            resource_ids.append(rid)
            rid += 1
        await session.execute(insert(ResourceModel), batch)
        inserted += batch_size

    # Mark ~5 % of resources as repointed to another resource
    repoint_count = max(1, total_resources // 20)
    repointed_ids = _RNG.sample(resource_ids[:-repoint_count], repoint_count)
    target_ids = _RNG.sample(
        [r for r in resource_ids if r not in set(repointed_ids)], repoint_count
    )
    from sqlalchemy import update as sa_update

    for rp_id, tgt_id in zip(repointed_ids, target_ids):
        await session.execute(
            sa_update(ResourceModel)
            .where(ResourceModel.id == rp_id)
            .values(repointed_id=tgt_id)
        )

    active_resource_ids = [r for r in resource_ids if r not in set(repointed_ids)]

    # ---- memberships -------------------------------------------------------
    # Each resource gets 1–3 memberships from different sources.
    # Assign sources round-robin across the pool so all four source keys are present.
    mem_batch: list[dict] = []
    mem_id = 1
    src_pool = source_ids[:]
    _RNG.shuffle(src_pool)

    src_idx = 0
    for res_id in active_resource_ids:
        n_memberships = _RNG.randint(1, 3)
        used_keys: set[str] = set()
        for _ in range(n_memberships):
            # pick a source with a key not yet used for this resource
            attempts = 0
            while attempts < 20:
                s_id = src_pool[src_idx % len(src_pool)]
                src_idx += 1
                s_key = source_key_by_id[s_id]
                if s_key not in used_keys:
                    used_keys.add(s_key)
                    break
                attempts += 1
            else:
                # No unused source key found (cannot happen with 4 distinct keys
                # and <=3 memberships per resource). Skip rather than add a
                # duplicate-key membership: two ACTIVE memberships of the same
                # source key trigger the documented v2-vs-old tiebreak divergence
                # and would make --compare-old report false mismatches.
                continue

            # ~8 % INACTIVE memberships
            status = (
                MembershipStatus.INACTIVE
                if _RNG.random() < 0.08
                else MembershipStatus.ACTIVE
            )
            mem_batch.append(
                {
                    "id": mem_id,
                    "resource_id": res_id,
                    "source": s_key,
                    "source_pk": s_id,
                    "status": status,
                    "created_by_id": user_id,
                    "last_updated_by_id": user_id,
                }
            )
            mem_id += 1

        if len(mem_batch) >= chunk:
            await session.execute(insert(MembershipModel), mem_batch)
            mem_batch = []

    if mem_batch:
        await session.execute(insert(MembershipModel), mem_batch)

    await session.flush()

    # ---- rebuild projection ------------------------------------------------
    t0 = time.perf_counter()
    await rebuild_all(session)
    rebuild_ms = (time.perf_counter() - t0) * 1000
    click.echo(f"rebuild_all completed in {rebuild_ms:.0f} ms")

    await session.flush()
    return engine, session


def build_matrix() -> list[OGFieldQueryParams]:
    """Return the benchmark parameter matrix (source kept at DEFAULT)."""
    return [
        OGFieldQueryParams(),  # default endpoint call (sorts by name asc)
        OGFieldQueryParams(q="perm"),  # q-search
        OGFieldQueryParams(country="USA"),  # exact filter (ISO-3)
        OGFieldQueryParams(sort_by="country"),  # sort by a (different) text field
        OGFieldQueryParams(sort_by="discovery_year"),  # sort by a year field
        OGFieldQueryParams(page=10, page_size=20),  # deep page
    ]


async def compare_all(
    session: AsyncSession,
    licensed_sources=None,
    *,
    compare_old: bool = False,
) -> list[dict]:
    """Time query_v2() for every matrix entry; return a list of result dicts.

    By default only the new query_v2() is run — the goal is to confirm the new
    path is fast. Pass ``compare_old=True`` to also run the old query() and
    assert identical ids/total (a correctness cross-check at scale). The old
    path is slow at scale, so each case streams progress when comparing.

    Each dict has keys: params, compared, new_ms, new_ids, new_total, and
    (when compared) old_ms, old_ids, old_total, ids_match, total_match.
    """
    matrix = build_matrix()
    results = []
    n = len(matrix)
    if compare_old:
        click.echo(
            f"Running {n} cases: old query() vs query_v2() (old is slow at scale) …"
        )
    else:
        click.echo(f"Running {n} cases against query_v2() …")

    for idx, params in enumerate(matrix, start=1):
        desc = _describe_params(params)
        old_ms = old_ids = old_total = ids_match = total_match = None

        if compare_old:
            click.echo(f"[{idx}/{n}] {desc}: running old query() …")
            t0 = time.perf_counter()
            old_items, old_total = await _old.query(session, params, licensed_sources)
            old_ms = (time.perf_counter() - t0) * 1000
            old_ids = [i.id for i in old_items]
            click.echo(f"[{idx}/{n}] {desc}: old={old_ms:.0f} ms; running query_v2() …")

        t1 = time.perf_counter()
        new_items, new_total = await _new.query_v2(session, params, licensed_sources)
        new_ms = (time.perf_counter() - t1) * 1000
        new_ids = [i.id for i in new_items]

        if compare_old:
            ids_match = old_ids == new_ids
            total_match = old_total == new_total
            speedup = old_ms / new_ms if new_ms > 0 else float("inf")
            ok = "OK" if (ids_match and total_match) else "FAIL"
            click.echo(
                f"[{idx}/{n}] {desc}: old={old_ms:.0f} ms  new={new_ms:.1f} ms  "
                f"{speedup:.0f}x  total={new_total}  {ok}"
            )
        else:
            click.echo(f"[{idx}/{n}] {desc}: new={new_ms:.1f} ms  total={new_total}")

        results.append(
            {
                "params": params,
                "compared": compare_old,
                "old_ms": old_ms,
                "new_ms": new_ms,
                "old_ids": old_ids,
                "new_ids": new_ids,
                "old_total": old_total,
                "new_total": new_total,
                "ids_match": ids_match,
                "total_match": total_match,
            }
        )

    return results


def _describe_params(params: OGFieldQueryParams) -> str:
    """Return a short human-readable description of the params."""
    parts = []
    if params.q:
        parts.append(f"q={params.q!r}")
    if params.country:
        parts.append(f"country={params.country!r}")
    if params.sort_by != "name":
        parts.append(f"sort_by={params.sort_by!r}")
    if params.sort_order != "asc":
        parts.append(f"order={params.sort_order}")
    if params.page != 1:
        parts.append(f"page={params.page}/size={params.page_size}")
    if not parts:
        return "default (sort by name)"
    return ", ".join(parts)


def _print_results(results: list[dict]) -> None:
    """Print the summary table; assert correctness when the old path was compared."""
    compared = bool(results and results[0]["compared"])
    click.echo("")
    if compared:
        header = f"{'Case':<32} {'Old ms':>10} {'New ms':>9} {'Speedup':>8} {'Total':>8} {'OK':>5}"
    else:
        header = f"{'Case':<32} {'New ms':>9} {'Total':>8}"
    click.echo(header)
    click.echo("-" * len(header))

    failed: list[dict] = []
    for r in results:
        label = _describe_params(r["params"])
        if compared:
            ok = "YES" if (r["ids_match"] and r["total_match"]) else "FAIL"
            if ok == "FAIL":
                failed.append(r)
            speedup = r["old_ms"] / r["new_ms"] if r["new_ms"] > 0 else float("inf")
            click.echo(
                f"{label:<32} {r['old_ms']:>10.0f} {r['new_ms']:>9.1f} "
                f"{speedup:>7.0f}x {r['new_total']:>8} {ok:>5}"
            )
        else:
            click.echo(f"{label:<32} {r['new_ms']:>9.1f} {r['new_total']:>8}")

    click.echo("")

    if compared:
        if failed:
            for r in failed:
                click.echo(
                    f"MISMATCH for params={r['params']}\n"
                    f"  old_ids[:5]={r['old_ids'][:5]}\n"
                    f"  new_ids[:5]={r['new_ids'][:5]}\n"
                    f"  old_total={r['old_total']}  new_total={r['new_total']}"
                )
            raise click.ClickException(
                f"{len(failed)} case(s) produced mismatched results — see above."
            )
        click.echo("All cases: old == new. Benchmark complete.")
    else:
        slowest = max(r["new_ms"] for r in results)
        click.echo(
            f"query_v2() complete — slowest case {slowest:.1f} ms across "
            f"{len(results)} cases. (Use --compare-old to cross-check vs the old query.)"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """Benchmark old query() vs new query_v2() on a seeded SQLite database."""


@cli.command()
@click.option("--rows", default=80_000, show_default=True, help="Rows to seed.")
@click.option(
    "--keep",
    is_flag=True,
    default=False,
    help="Keep the on-disk SQLite file after the run.",
)
@click.option(
    "--compare-old",
    "compare_old",
    is_flag=True,
    default=False,
    help="Also run the old query() and assert identical ids/total (slow at scale).",
)
@click.option(
    "--profile",
    "do_profile",
    is_flag=True,
    default=False,
    help="Wrap the run in cProfile and print stats.",
)
def run(rows: int, keep: bool, compare_old: bool, do_profile: bool):
    """Build a seeded SQLite DB and time query_v2() (optionally vs the old query)."""

    async def _main():
        with tempfile.NamedTemporaryFile(
            suffix=".sqlite", delete=False, prefix="stitch_bench_"
        ) as tmp:
            tmp_path = tmp.name

        click.echo(f"Building DB at {tmp_path} with {rows:,} rows …")
        engine, session = await build_db(rows=rows, file_path=tmp_path)

        try:
            if do_profile:
                pr = cProfile.Profile()
                pr.enable()

            results = await compare_all(session, compare_old=compare_old)

            if do_profile:
                pr.disable()
                buf = io.StringIO()
                ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
                ps.print_stats(30)
                click.echo(buf.getvalue())

            _print_results(results)
        finally:
            await session.close()
            await engine.dispose()
            if not keep:
                Path(tmp_path).unlink(missing_ok=True)
            else:
                click.echo(f"SQLite file retained: {tmp_path}")

    asyncio.run(_main())


if __name__ == "__main__":
    cli()
