#!/usr/bin/env python
"""Propose fuzzy duplicate groups from scripts/data/resources.jsonl.

Throwaway demo helper -- not shipped code, not committed.

    uv run --with rapidfuzz --with numpy scripts/find_candidates.py

This script is deliberately recall-oriented. It PROPOSES groups and explains
why, and never decides: every group comes out with "decision": null for a
human or an AI to fill in with "merge" or "skip".
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Iterable

import numpy as np
from rapidfuzz import fuzz, process

from _common import CANDIDATES_PATH, DATA_DIR, RESOURCES_PATH


# Longest first: stripping is repeated until nothing more matches.
TYPE_PHRASES = (
    "oil and gas field",
    "oil and gas asset",
    "cbm gas field",
    "tight gas field",
    "oil and gas",
    "oil field",
    "gas field",
    "oil asset",
    "gas asset",
    "oil phase",
    "gas phase",
    "field",
    "asset",
    "phase",
)

# "10097UUU/Athabasca Oil Asset (Alberta, Canada)" -> drop the record-id prefix.
ID_PREFIX_RE = re.compile(r"^\s*\d+[A-Za-z]*\s*/\s*")
PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")
SEGMENT_SPLIT_RE = re.compile(r"\s+-\s+")
PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")

# Tokens that turn one field into a *different* field: 'blueberry east' is not
# 'blueberry west'. If such a token is on one side of a pair and not the other,
# the two are distinct assets no matter how similar the strings look.
QUALIFIER_TOKENS = frozenset(
    {
        "north",
        "south",
        "east",
        "west",
        "n",
        "s",
        "e",
        "w",
        "ne",
        "nw",
        "se",
        "sw",
        "northeast",
        "northwest",
        "southeast",
        "southwest",
        "central",
        "upper",
        "lower",
        "deep",
        "shallow",
        "main",
        "extension",
        "ext",
        "unit",
        "i",
        "ii",
        "iii",
        "iv",
        "v",
        "vi",
    }
)

EARTH_RADIUS_KM = 6371.0088


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tidy(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    cleaned = PUNCT_RE.sub(" ", strip_accents(text).casefold())
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def strip_type_phrases(text: str) -> str:
    """Repeatedly remove trailing asset-type words: 'darquain oil field' -> 'darquain'."""
    current = text
    changed = True
    while changed:
        changed = False
        for phrase in TYPE_PHRASES:
            if current.endswith(" " + phrase):
                current = current[: -(len(phrase) + 1)].strip()
                changed = True
                break
    return current


def split_name(raw_name: str) -> tuple[list[str], list[str]]:
    """Split a raw name into (segments, parentheticals).

    Parentheticals are pulled out wherever they appear; the remaining text is
    split on ' - ' into segments, each tidied and stripped of type phrases.
    """
    without_prefix = ID_PREFIX_RE.sub("", raw_name)
    parentheticals = [
        tidy(match) for match in PARENTHETICAL_RE.findall(without_prefix) if tidy(match)
    ]
    body = PARENTHETICAL_RE.sub(" ", without_prefix)

    segments = []
    for part in SEGMENT_SPLIT_RE.split(body):
        segment = strip_type_phrases(tidy(part))
        if segment:
            segments.append(segment)
    return segments, parentheticals


def name_keys(segments: list[str]) -> list[str]:
    """Blocking keys for a name.

    The whole core, plus each ' - ' segment on its own, because GEM writes both
    '<Place> - <Operator> Gas Asset' and '<Operator> - <Place> Gas Asset' and we
    cannot reliably tell which half is the field.
    """
    if not segments:
        return []
    keys = {" ".join(segments)}
    if len(segments) > 1:
        keys.update(segments)
    return sorted(keys)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class UnionFind:
    def __init__(self) -> None:
        self._parent: dict[int, int] = {}
        self._size: dict[int, int] = {}

    def find(self, item: int) -> int:
        self._parent.setdefault(item, item)
        self._size.setdefault(item, 1)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def size_of(self, item: int) -> int:
        return self._size[self.find(item)]

    def union(self, left: int, right: int) -> bool:
        """Merge two clusters. Returns False if they were already together."""
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return False
        self._parent[right_root] = left_root
        self._size[left_root] += self._size[right_root]
        return True

    def groups(self) -> dict[int, list[int]]:
        clusters: dict[int, list[int]] = defaultdict(list)
        for item in self._parent:
            clusters[self.find(item)].append(item)
        return clusters


def load_records(path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def prepare(records: Iterable[dict[str, Any]], location_min_count: int) -> list[dict]:
    """Attach normalized keys and discriminators to each record."""
    prepared = []
    for record in records:
        segments, parentheticals = split_name(record.get("name") or "")
        prepared.append(
            {
                **record,
                "segments": segments,
                "core": " ".join(segments),
                "parentheticals": parentheticals,
                "keys": name_keys(segments),
            }
        )

    # A parenthetical seen on many records is boilerplate location text
    # ("(iran)", "(alberta canada)"). A rare one discriminates ("(lamadian)",
    # "(mc782)") and must block a join. This is learned from the corpus rather
    # than from a hardcoded country list.
    counts = Counter(
        paren for record in prepared for paren in set(record["parentheticals"])
    )
    for record in prepared:
        record["discriminators"] = sorted(
            {
                paren
                for paren in record["parentheticals"]
                if counts[paren] < location_min_count
            }
        )

    # In '<A> - <B> Gas Asset' one half is the field and the other is the
    # operator, and GEM writes it both ways round. The operator half recurs
    # across many assets, the field half does not, so the rarest segment of a
    # name is its anchor. Joining on a non-anchor segment is what produces
    # 'Belmont County - Ascent' ~ 'Harrison County - Ascent': two different
    # fields sharing an operator.
    segment_counts = Counter(
        segment for record in prepared for segment in set(record["segments"])
    )
    for record in prepared:
        segments = record["segments"]
        if segments:
            rarest = min(segment_counts[segment] for segment in segments)
            record["anchors"] = {
                segment for segment in segments if segment_counts[segment] == rarest
            }
        else:
            record["anchors"] = set()
    return prepared


def key_anchors_pair(key: str, left: dict, right: dict) -> bool:
    """May ``key`` join these two records?

    Always yes when it is a whole name, or when either side is a single-segment
    name (the bare-name-versus-decorated-name case this tool exists for).
    Otherwise the key must be the rarest segment on *both* sides.
    """
    if key in (left["core"], right["core"]):
        return True
    if len(left["segments"]) == 1 or len(right["segments"]) == 1:
        return True
    return key in left["anchors"] and key in right["anchors"]


def discriminators_conflict(left: dict, right: dict) -> bool:
    """Two records with different rare parentheticals are different assets."""
    left_set, right_set = set(left["discriminators"]), set(right["discriminators"])
    if not left_set or not right_set:
        return False
    return left_set.isdisjoint(right_set)


def qualifiers_conflict(left: dict, right: dict) -> bool:
    """One side carries a directional/ordinal token the other does not."""
    only_one_side = set(left["core"].split()).symmetric_difference(
        right["core"].split()
    )
    return any(token in QUALIFIER_TOKENS or token.isdigit() for token in only_one_side)


def edge_vetoed(left: dict, right: dict) -> bool:
    return discriminators_conflict(left, right) or qualifiers_conflict(left, right)


def exact_edges(
    prepared: list[dict], max_key_frequency: int
) -> tuple[list[tuple[int, int, str]], list[tuple[str, int]]]:
    """Pairs sharing a blocking key, ignoring keys too common to discriminate."""
    by_key: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(prepared):
        for key in record["keys"]:
            by_key[key].append(index)

    edges: list[tuple[int, int, str]] = []
    suppressed: list[tuple[str, int]] = []
    for key, indexes in by_key.items():
        if len(indexes) < 2:
            continue
        if len(indexes) > max_key_frequency:
            suppressed.append((key, len(indexes)))
            continue
        for position, left in enumerate(indexes):
            for right in indexes[position + 1 :]:
                if key_anchors_pair(key, prepared[left], prepared[right]):
                    edges.append((left, right, key))
    return edges, sorted(suppressed, key=lambda pair: -pair[1])


def similarity_edges(
    prepared: list[dict],
    fuzzy_threshold: int,
    geo_name_threshold: int,
    geo_km: float,
) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int, float]]]:
    """Fuzzy and geo pairs, computed per country bucket off one cdist matrix."""
    buckets: dict[str | None, list[int]] = defaultdict(list)
    for index, record in enumerate(prepared):
        buckets[record.get("country")].append(index)

    fuzzy: list[tuple[int, int, int]] = []
    geo: list[tuple[int, int, int, float]] = []
    floor = min(fuzzy_threshold, geo_name_threshold)

    for indexes in buckets.values():
        if len(indexes) < 2:
            continue
        cores = [prepared[index]["core"] for index in indexes]
        scores = process.cdist(
            cores,
            cores,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=floor,
            workers=-1,
        )
        left_positions, right_positions = np.nonzero(np.triu(scores, k=1))
        for left_position, right_position in zip(left_positions, right_positions):
            left = indexes[int(left_position)]
            right = indexes[int(right_position)]
            score = int(scores[left_position, right_position])
            if score >= fuzzy_threshold:
                fuzzy.append((left, right, score))
                continue
            distance = pair_distance_km(prepared[left], prepared[right])
            if distance is not None and distance <= geo_km:
                geo.append((left, right, score, distance))
    return fuzzy, geo


def pair_distance_km(left: dict, right: dict) -> float | None:
    if None in (
        left.get("latitude"),
        left.get("longitude"),
        right.get("latitude"),
        right.get("longitude"),
    ):
        return None
    return haversine_km(
        left["latitude"], left["longitude"], right["latitude"], right["longitude"]
    )


CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def classify_confidence(group: dict) -> str:
    """How much a group deserves to be trusted without close reading.

    'high' is the pass-one tier: a clean two-record pair, joined on an exact
    normalized name, in one country, contributed by two different sources. That
    is the bare-name-versus-decorated-name duplicate this tool was built for,
    and it is the shape entity-linkage misses entirely today.
    """
    signals = group["signals"]
    exact = "exact-normalized-name" in group["reasons"]
    size = len(group["resource_ids"])
    similarity = signals["min_name_similarity"] or 0

    if (
        exact
        and size == 2
        and signals["same_country"]
        and not signals["single_source"]
        and not signals["discriminators"]
    ):
        return "high"
    if exact and size <= 3 and signals["same_country"]:
        return "medium"
    if similarity >= 95 and size == 2 and signals["same_country"]:
        return "medium"
    return "low"


def build_groups(
    prepared: list[dict],
    edges: list[tuple[int, int, str, Any]],
    max_group_size: int,
) -> tuple[list[dict], list[tuple[int, int]]]:
    """Cluster the surviving edges, then assemble reviewable groups."""
    reasons_by_pair: dict[tuple[int, int], set[str]] = defaultdict(set)
    scores_by_pair: dict[tuple[int, int], int] = {}
    distance_by_pair: dict[tuple[int, int], float] = {}

    for left, right, reason, detail in edges:
        if edge_vetoed(prepared[left], prepared[right]):
            continue
        pair = (min(left, right), max(left, right))
        reasons_by_pair[pair].add(reason)
        if reason == "exact-normalized-name":
            scores_by_pair[pair] = 100
        elif reason == "fuzzy-name":
            scores_by_pair[pair] = max(scores_by_pair.get(pair, 0), int(detail))
        elif reason == "geo-proximity":
            score, distance = detail
            scores_by_pair[pair] = max(scores_by_pair.get(pair, 0), int(score))
            distance_by_pair[pair] = distance

    # Agglomerate strongest edge first, refusing any join that would push a
    # cluster past --max-group-size. Dropping whole oversized components (the
    # obvious alternative) silently discards the strong exact-name pairs buried
    # inside a geo-chained blob, so instead the weakest edges are the ones that
    # lose. Ties break on resource id, so a run is reproducible.
    def edge_strength(pair: tuple[int, int]) -> tuple[int, int, int, int]:
        reasons = reasons_by_pair[pair]
        if "exact-normalized-name" in reasons:
            tier = 3
        elif "fuzzy-name" in reasons:
            tier = 2
        else:
            tier = 1
        return (-tier, -scores_by_pair.get(pair, 0), pair[0], pair[1])

    union = UnionFind()
    deferred: list[tuple[int, int]] = []
    for pair in sorted(reasons_by_pair, key=edge_strength):
        left, right = pair
        if union.find(left) == union.find(right):
            continue
        if union.size_of(left) + union.size_of(right) > max_group_size:
            deferred.append(pair)
            continue
        union.union(left, right)

    groups: list[dict] = []

    for members in union.groups().values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda index: prepared[index]["id"])
        records = [prepared[index] for index in members]
        pairs = [
            (min(a, b), max(a, b))
            for position, a in enumerate(members)
            for b in members[position + 1 :]
        ]
        known_pairs = [pair for pair in pairs if pair in reasons_by_pair]

        reasons = sorted({r for pair in known_pairs for r in reasons_by_pair[pair]})
        similarities = [scores_by_pair[p] for p in known_pairs if p in scores_by_pair]
        distances = [distance_by_pair[p] for p in known_pairs if p in distance_by_pair]
        countries = sorted({r["country"] for r in records if r.get("country")})
        sources = sorted({s for r in records for s in r.get("sources") or []})

        group = {
            "resource_ids": [r["id"] for r in records],
            "reasons": reasons,
            "signals": {
                "normalized_names": sorted({r["core"] for r in records}),
                "min_name_similarity": min(similarities) if similarities else None,
                "countries": countries,
                "same_country": len(countries) <= 1,
                "max_distance_km": round(max(distances), 2) if distances else None,
                "discriminators": sorted(
                    {d for r in records for d in r["discriminators"]}
                ),
                "sources": sources,
                "single_source": len(sources) <= 1,
            },
            "members": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "country": r["country"],
                    "basin": r["basin"],
                    "state_province": r["state_province"],
                    "operators": r["operators"],
                    "sources": r["sources"],
                }
                for r in records
            ],
            "decision": None,
            "reason": None,
        }

        group["confidence"] = classify_confidence(group)
        groups.append(group)

    # Most trustworthy first: exact-key, cross-source, same-country, tightest.
    groups.sort(
        key=lambda g: (
            CONFIDENCE_ORDER[g["confidence"]],
            "exact-normalized-name" not in g["reasons"],
            g["signals"]["single_source"],
            not g["signals"]["same_country"],
            -(g["signals"]["min_name_similarity"] or 0),
            len(g["resource_ids"]),
        )
    )
    return groups, deferred


def summarize(
    groups: list[dict], deferred, prepared, suppressed_keys, withheld
) -> None:
    print(f"\n{len(groups)} candidate groups proposed", file=sys.stderr)

    if withheld:
        detail = ", ".join(f"{count} {tier}" for tier, count in withheld.most_common())
        print(
            f"  ({detail} withheld by --min-confidence; re-run wider after "
            "merging this tier)",
            file=sys.stderr,
        )

    by_confidence = Counter(g["confidence"] for g in groups)
    for tier, count in sorted(
        by_confidence.items(), key=lambda kv: CONFIDENCE_ORDER[kv[0]]
    ):
        print(f"  confidence {tier:<18} {count}", file=sys.stderr)

    by_reason = Counter(reason for g in groups for reason in g["reasons"])
    for reason, count in by_reason.most_common():
        print(f"  reason {reason:<22} {count}", file=sys.stderr)

    sizes = Counter(len(g["resource_ids"]) for g in groups)
    for size in sorted(sizes):
        print(f"  size {size:<24} {sizes[size]}", file=sys.stderr)

    cross_source = sum(1 for g in groups if not g["signals"]["single_source"])
    cross_country = sum(1 for g in groups if not g["signals"]["same_country"])
    print(f"  cross-source groups        {cross_source}", file=sys.stderr)
    print(f"  single-source groups       {len(groups) - cross_source}", file=sys.stderr)
    print(f"  cross-country groups       {cross_country}", file=sys.stderr)

    if deferred:
        print(
            f"\n{len(deferred)} edge(s) not applied because the cluster had "
            "already reached --max-group-size:",
            file=sys.stderr,
        )
        for left, right in deferred[:10]:
            left_name = (prepared[left]["name"] or "")[:34]
            right_name = (prepared[right]["name"] or "")[:34]
            print(f"  {left_name}  ~  {right_name}", file=sys.stderr)

    if suppressed_keys:
        print(
            f"\n{len(suppressed_keys)} blocking key(s) ignored as too common "
            "(likely operator names); raise --max-key-frequency to include them:",
            file=sys.stderr,
        )
        for key, count in suppressed_keys[:10]:
            print(f"  {count:>4}x  {key}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuzzy-threshold", type=int, default=90)
    parser.add_argument("--geo-km", type=float, default=10.0)
    parser.add_argument("--geo-name-threshold", type=int, default=70)
    parser.add_argument("--max-group-size", type=int, default=6)
    parser.add_argument(
        "--max-key-frequency",
        type=int,
        default=6,
        help="ignore a blocking key shared by more than this many resources",
    )
    parser.add_argument(
        "--location-min-count",
        type=int,
        default=5,
        help="a parenthetical seen at least this often is boilerplate location text",
    )
    parser.add_argument(
        "--min-confidence",
        choices=("high", "medium", "low"),
        default="high",
        help=(
            "only emit groups at this confidence or better (default: high). "
            "Merge the high tier first, re-fetch, then re-run wider."
        ),
    )
    parser.add_argument("--in", dest="in_path", default=str(RESOURCES_PATH))
    parser.add_argument("--out", dest="out_path", default=str(CANDIDATES_PATH))
    args = parser.parse_args()

    from pathlib import Path

    records = load_records(Path(args.in_path))
    print(f"loaded {len(records)} records", file=sys.stderr)

    prepared = prepare(records, args.location_min_count)

    exact, suppressed_keys = exact_edges(prepared, args.max_key_frequency)
    fuzzy, geo = similarity_edges(
        prepared, args.fuzzy_threshold, args.geo_name_threshold, args.geo_km
    )
    print(
        f"edges: exact={len(exact)} fuzzy={len(fuzzy)} geo={len(geo)}", file=sys.stderr
    )

    edges: list[tuple[int, int, str, Any]] = []
    edges.extend(
        (left, right, "exact-normalized-name", key) for left, right, key in exact
    )
    edges.extend((left, right, "fuzzy-name", score) for left, right, score in fuzzy)
    edges.extend(
        (left, right, "geo-proximity", (score, distance))
        for left, right, score, distance in geo
    )

    groups, deferred = build_groups(prepared, edges, args.max_group_size)

    withheld = Counter(
        group["confidence"]
        for group in groups
        if CONFIDENCE_ORDER[group["confidence"]] > CONFIDENCE_ORDER[args.min_confidence]
    )
    groups = [
        group
        for group in groups
        if CONFIDENCE_ORDER[group["confidence"]]
        <= CONFIDENCE_ORDER[args.min_confidence]
    ]
    for position, group in enumerate(groups, start=1):
        group["group_id"] = f"g{position:04d}"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_from": args.in_path,
        "params": {
            "fuzzy_threshold": args.fuzzy_threshold,
            "geo_km": args.geo_km,
            "geo_name_threshold": args.geo_name_threshold,
            "max_group_size": args.max_group_size,
            "max_key_frequency": args.max_key_frequency,
            "location_min_count": args.location_min_count,
            "min_confidence": args.min_confidence,
        },
        "groups": groups,
    }
    Path(args.out_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summarize(groups, deferred, prepared, suppressed_keys, withheld)
    print(f"\nwrote {len(groups)} groups to {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
