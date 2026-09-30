"""STIT-763 spike: every filter option in ONE query.

Self-contained. Builds its own statement from the ORM model classes and shares
nothing with `stitch.api.db.queries`. Nothing in the API package is touched.

Run against the local docker Postgres:

    make dev-docker                 # or: docker compose up -d db
    uv run --package stitch-api python scripts/stit763_options_spike.py

    # narrow to a licence set, more runs, show the SQL
    uv run --package stitch-api python scripts/stit763_options_spike.py \
        --sources gem,wm --runs 10 --show-sql

The curator override tier IS included. It decides which value wins whenever a
curator has re-ranked the sources for a field of a resource, so leaving it out
would let this script disagree with production on real data and make the diff
against `stit763_options_baseline.py` uninterpretable.

Simplifications against production `filter_options`, none of which should change
the result. Confirm that with the baseline script rather than assuming it:

  1. No `og_field_resources` join. Merging repoints a resource and sets its old
     memberships INACTIVE (`_repoint_memberships`), so `status = ACTIVE` already
     excludes them and the `repointed_id IS NULL` check is redundant.
  2. `value_text` only, no per-field column selection. All eight fields below are
     ValueKind.TEXT.
  3. No `value_text IS NOT NULL` filter. Rows only exist for attributes a source
     actually carries, and empty text cannot be persisted (write-path skip plus
     the ck_source_value_text_nonempty CHECK).
  4. No `oil_gas_field_sources` join. Production joins it as a
     (source, source_pk) consistency guard and selects nothing from it.
  5. The override join drops production's `o.source = m.source` term. That term
     guards against a stray override row whose (source, source_pk) pair is
     mismatched. The remaining three columns are the table's full primary key,
     so the join still cannot fan out.

ROW_NUMBER() rather than Postgres DISTINCT ON: the API test suite runs on SQLite,
so a version of this that ever ships has to compile on both.

What the diff has actually confirmed, on the populated local database:

  * Identical to production for all four licence profiles a real user can hold,
    and the profiles differ from each other, so parity is not an artefact of
    licensing having no effect on this corpus.
  * The override tier is exercised. og_field_resource_source_priority holds
    109,748 rows -- 36,568 curated (resource, field) pairs across 5,474
    resources -- so the outer join and simplification 5 run on real data.
  * Measured: 733ms for the six fields the Resource List page loads today,
    against 228ms for this one query.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Collection
from statistics import mean

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from _common import open_session
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceSourcePriority,
    OGFieldSourcePriority,
    OilGasFieldSourceValueModel,
)

# The filterable fields, per the design doc: every coalesced text attribute
# except name and name_local, which are near-unique per resource.
FIELDS = (
    "basin",
    "country",
    "field_status",
    "location_type",
    "primary_hydrocarbon_group",
    "production_conventionality",
    "region",
    "state_province",
)


def build_statement(licensed_sources: Collection[str] | None) -> Select:
    """Distinct coalesced winner values for every field in FIELDS, one pass.

    ROW_NUMBER() partitions by (resource_id, colname), so one pass picks the
    winner for every field at once. rn == 1 is the winner. DISTINCT is over the
    (colname, value) pair, so a string that is a valid value for two fields
    survives as two rows and lands under both.

    The ranking is tiered, matching production: a value a curator has re-ranked
    (an override row exists, so o.priority is NOT NULL) beats every value that
    has not been, which is what NULLS LAST buys. Within a tier, the global
    default source priority decides.
    """
    m = MembershipModel
    v = OilGasFieldSourceValueModel
    p = OGFieldSourcePriority
    o = OGFieldResourceSourcePriority

    ranked = (
        select(
            v.colname,
            v.value_text,
            func.row_number()
            .over(
                partition_by=(m.resource_id, v.colname),
                order_by=(
                    o.priority.asc().nulls_last(),
                    p.priority.asc(),
                    # Required, not a tiebreak of convenience: one resource can
                    # hold several ACTIVE records from the SAME source, which tie
                    # on p.priority (unique per source). Without these the winner
                    # is whatever the database happens to pick, so the endpoint
                    # can return a different value set on identical calls.
                    m.source.asc(),
                    m.source_pk.asc(),
                ),
            )
            .label("rn"),
        )
        .select_from(m)
        .join(v, v.source_pk == m.source_pk)
        .join(p, p.source == m.source)
        # At the value grain, and on the override table's full primary key
        # (resource_id, source_pk, colname), so at most one override row per
        # value row: the outer join cannot fan out.
        .outerjoin(
            o,
            and_(
                o.resource_id == m.resource_id,
                o.source_pk == m.source_pk,
                o.colname == v.colname,
            ),
        )
        .where(
            m.status == MembershipStatus.ACTIVE,
            v.colname.in_(FIELDS),
        )
    )
    if licensed_sources is not None:
        ranked = ranked.where(m.source.in_(licensed_sources))
    ranked = ranked.subquery()

    return (
        select(ranked.c.colname, ranked.c.value_text)
        .where(ranked.c.rn == 1)
        .distinct()
        .order_by(ranked.c.colname, ranked.c.value_text)
    )


async def fetch_options(
    session: AsyncSession, licensed_sources: Collection[str] | None
) -> dict[str, list[str]]:
    """Run the statement and group the (colname, value) pairs by field.

    Every field is present, empty list included. Grouping appends into a
    pre-seeded dict, so it does not depend on the SQL ORDER BY.
    """
    options: dict[str, list[str]] = {field: [] for field in FIELDS}
    rows = await session.execute(build_statement(licensed_sources))
    for colname, value in rows:
        options[colname].append(value)
    return options


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="timed runs (default 5)")
    parser.add_argument(
        "--sources",
        default=None,
        help="comma-separated licence set, e.g. gem,wm (default: all sources)",
    )
    parser.add_argument("--show-sql", action="store_true", help="print the SQL")
    args = parser.parse_args()

    sources = args.sources.split(",") if args.sources else None

    if args.show_sql:
        print(f"\n{build_statement(sources)}\n")

    async with open_session() as session:
        print(f"sources: {','.join(sources) if sources else 'all'}")

        # Warm-up, not timed: the first query pays connection setup and planning.
        options = await fetch_options(session, sources)

        elapsed = []
        for _ in range(args.runs):
            start = time.perf_counter()
            await fetch_options(session, sources)
            elapsed.append((time.perf_counter() - start) * 1000)

    print(f"\noptions ({sum(len(v) for v in options.values())} values total)")
    for field in FIELDS:
        values = options[field]
        sample = ", ".join(values[:4]) + (", ..." if len(values) > 4 else "")
        print(f"  {field:<28} {len(values):>6}  {sample}")

    print(f"\n1 query x {args.runs} runs, ms")
    print(
        f"  min {min(elapsed):8.1f}   mean {mean(elapsed):8.1f}   max {max(elapsed):8.1f}"
    )


if __name__ == "__main__":
    asyncio.run(main())
