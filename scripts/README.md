# Duplicate-hunting scripts (throwaway)

Not shipped code, not committed (`scripts/` is in `.git/info/exclude`).

Finds likely-duplicate oil & gas field resources far more loosely than the
`entity-linkage` deployment does, records the proposed sets locally for review,
then creates and approves merge candidates from the reviewed file.

## Why

`entity-linkage` blocks on `name.strip().casefold()` and confirms on
`country.strip().upper()` — both exact. On the demo corpus (9,187 resources)
that finds **zero** groups, because GEM writes `Darquain Oil Field (Iran)` while
CCR/BC/WM write `Darquain`. Normalizing the decoration away finds 273
high-confidence pairs on the same data.

## Workflow

```bash
# 1. snapshot the corpus (always fetches everything; a few seconds)
uv run scripts/fetch_resources.py

# 2. propose candidate groups (high-confidence tier only by default)
uv run --with rapidfuzz --with numpy scripts/find_candidates.py

# 3. review: edit data/candidates.json, setting "decision" to "merge" or "skip"
#    and "reason" to one line of justification, for every group.

# 4. create merge candidates from the reviewed file
uv run scripts/create_merge_candidate.py --from-file --dry-run
uv run scripts/create_merge_candidate.py --from-file --limit 3

# 5. approve or deny
uv run scripts/review_merge_candidates.py list --mine
uv run scripts/review_merge_candidates.py approve 20 --notes "why"
```

Approving mints a **new** resource, so the snapshot goes stale. Re-run step 1
before searching again.

## Prioritise, then widen

`find_candidates.py` classifies every group and emits only the `high` tier by
default:

- **high** — an exact normalized-name pair, one country, two different sources,
  no conflicting parenthetical. The bare-vs-decorated duplicate.
- **medium** — exact normalized name but same-source, or a 3-way group, or a
  very close fuzzy pair.
- **low** — everything else: geo-linked clusters, operator-split assets.

Merge the high tier, re-fetch, re-run. Each pass makes the next tier cleaner
than analysing everything at once. Widen with `--min-confidence medium|low`.

## How the matching works

Normalization strips accents, a leading `12345AB/` id prefix, trailing
`(location)` parentheticals, and trailing type phrases (`Oil and Gas Field`,
`Gas Asset`, `Oil Phase`, …), then casefolds and collapses punctuation.

Three blocking passes are unioned:

- **exact** — identical normalized name. A name split on ` - ` also blocks on
  each half, but only when that half is the *rarest* segment on both sides,
  otherwise `Belmont County - Ascent` matches `Harrison County - Ascent` on the
  operator.
- **fuzzy** — `token_sort_ratio >= 90` within a country bucket. Not
  `token_set_ratio`: it scores `MARTIN` against `MARTIN CREEK` at 100 and chains
  the corpus into one 1,000-member blob.
- **geo** — within 10 km and name similarity >= 70.

Two vetoes kill an edge before clustering:

- **conflicting discriminators** — a rare parenthetical that only some records
  carry, e.g. `Daqing (Lamadian)` vs `Daqing (Saertu)`, or `(MC782)` vs `(DC134)`.
  Rarity is learned from the corpus, so `(Iran)` is boilerplate and ignored.
- **conflicting qualifiers** — a directional or ordinal token on one side only:
  `Blueberry East` is not `Blueberry West`.

Clustering agglomerates the strongest edge first and refuses any join that would
push a cluster past `--max-group-size`, so weak geo edges lose rather than strong
exact-name pairs being dropped inside an oversized blob.
