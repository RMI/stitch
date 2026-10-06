#!/usr/bin/env python
"""Propose undecided fuzzy duplicate groups: uv run --with rapidfuzz --with numpy."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, NamedTuple

import numpy as np
from rapidfuzz import fuzz, process

from lib.candidates import (
    CANDIDATES_PATH,
    CONFIDENCE_ORDER,
    RESOURCES_PATH,
    write_payload,
)


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

ID_PREFIX_RE = re.compile(r"^\s*\d+[A-Za-z]*\s*/\s*")
PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")
SEGMENT_SPLIT_RE = re.compile(r"\s+-\s+")
PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")

QUALIFIER_TOKENS = frozenset(
    "north south east west n s e w ne nw se sw "
    "northeast northwest southeast southwest "
    "central upper lower deep shallow main extension ext unit "
    "i ii iii iv v vi".split()
)

EARTH_RADIUS_KM = 6371.0088

EXACT_NAME = "exact-normalized-name"
FUZZY_NAME = "fuzzy-name"
GEO_PROXIMITY = "geo-proximity"

Pair = tuple[int, int]


class Edge(NamedTuple):
    """One pass proposing one link, with the evidence it found."""

    left: int
    right: int
    reason: str
    score: int
    distance_km: float | None = None


@dataclass
class PairEvidence:
    """Everything every pass noticed about one pair, folded together."""

    reasons: set[str] = field(default_factory=set)
    score: int = 0
    distance_km: float | None = None


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tidy(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    cleaned = PUNCT_RE.sub(" ", strip_accents(text).casefold())
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def strip_type_phrases(text: str) -> str:
    """Remove trailing asset-type words, longest phrase first: 'oil field' before 'field'."""
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
    """Split a raw name into (segments, parentheticals), tidied and type-stripped."""
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
    """Blocking keys for a name: the whole core, plus each ' - ' segment alone."""
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


def load_records(path: Path) -> list[dict[str, Any]]:
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
        core = " ".join(segments)
        prepared.append(
            {
                **record,
                "segments": segments,
                "core": core,
                "tokens": frozenset(core.split()),
                "parentheticals": parentheticals,
                "keys": name_keys(segments),
            }
        )

    attach_discriminators(prepared, location_min_count)
    attach_anchors(prepared)
    return prepared


def attach_discriminators(prepared: list[dict], location_min_count: int) -> None:
    """Mark the rare parentheticals on each record: the ones that must block a join."""
    counts = Counter(
        paren for record in prepared for paren in set(record["parentheticals"])
    )
    for record in prepared:
        record["discriminators"] = frozenset(
            paren
            for paren in record["parentheticals"]
            if counts[paren] < location_min_count
        )


def attach_anchors(prepared: list[dict]) -> None:
    """Mark the rarest segment(s) of each name: the field half, not the operator half."""
    segment_counts = Counter(
        segment for record in prepared for segment in set(record["segments"])
    )
    for record in prepared:
        segments = record["segments"]
        if not segments:
            record["anchors"] = frozenset()
            continue
        rarest = min(segment_counts[segment] for segment in segments)
        record["anchors"] = frozenset(
            segment for segment in segments if segment_counts[segment] == rarest
        )


def key_anchors_pair(key: str, left: dict, right: dict) -> bool:
    """May ``key`` join these two records? A whole name, a bare name, or a shared anchor."""
    if key in (left["core"], right["core"]):
        return True
    if len(left["segments"]) == 1 or len(right["segments"]) == 1:
        return True
    return key in left["anchors"] and key in right["anchors"]


def discriminators_conflict(left: dict, right: dict) -> bool:
    """Two records with different rare parentheticals are different assets."""
    left_set, right_set = left["discriminators"], right["discriminators"]
    if not left_set or not right_set:
        return False
    return left_set.isdisjoint(right_set)


def qualifiers_conflict(left: dict, right: dict) -> bool:
    """One side carries a directional/ordinal token the other does not."""
    only_one_side = left["tokens"].symmetric_difference(right["tokens"])
    return any(token in QUALIFIER_TOKENS or token.isdigit() for token in only_one_side)


def edge_vetoed(left: dict, right: dict) -> bool:
    return discriminators_conflict(left, right) or qualifiers_conflict(left, right)


def exact_edges(
    prepared: list[dict], max_key_frequency: int
) -> tuple[list[Edge], list[tuple[str, int]]]:
    """Pairs sharing a blocking key, ignoring keys too common to discriminate."""
    by_key: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(prepared):
        for key in record["keys"]:
            by_key[key].append(index)

    edges: list[Edge] = []
    suppressed: list[tuple[str, int]] = []
    for key, indexes in by_key.items():
        if len(indexes) < 2:
            continue
        if len(indexes) > max_key_frequency:
            suppressed.append((key, len(indexes)))
            continue
        for left, right in combinations(indexes, 2):
            if key_anchors_pair(key, prepared[left], prepared[right]):
                edges.append(Edge(left, right, EXACT_NAME, 100))
    return edges, sorted(suppressed, key=lambda pair: -pair[1])


def similarity_edges(
    prepared: list[dict],
    fuzzy_threshold: int,
    geo_name_threshold: int,
    geo_km: float,
) -> list[Edge]:
    """Fuzzy and geo pairs, computed per country bucket off one cdist matrix."""
    buckets: dict[str | None, list[int]] = defaultdict(list)
    for index, record in enumerate(prepared):
        buckets[record.get("country")].append(index)

    edges: list[Edge] = []
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
                edges.append(Edge(left, right, FUZZY_NAME, score))
                continue
            distance = pair_distance_km(prepared[left], prepared[right])
            if distance is not None and distance <= geo_km:
                edges.append(Edge(left, right, GEO_PROXIMITY, score, distance))
    return edges


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


def classify_confidence(group: dict) -> str:
    """How much a group deserves to be trusted without close reading."""
    signals = group["signals"]
    exact = EXACT_NAME in group["reasons"]
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


def collect_evidence(
    prepared: list[dict], edges: list[Edge]
) -> dict[Pair, PairEvidence]:
    """Fold every pass's edges into one entry per surviving pair."""
    evidence: dict[Pair, PairEvidence] = {}
    for edge in edges:
        if edge_vetoed(prepared[edge.left], prepared[edge.right]):
            continue
        pair = (min(edge.left, edge.right), max(edge.left, edge.right))
        entry = evidence.setdefault(pair, PairEvidence())
        entry.reasons.add(edge.reason)
        entry.score = max(entry.score, edge.score)
        if edge.distance_km is not None:
            entry.distance_km = edge.distance_km
    return evidence


def cluster_pairs(
    evidence: dict[Pair, PairEvidence], max_group_size: int
) -> tuple[UnionFind, list[Pair]]:
    """Agglomerate the pairs, strongest edge first, stopping at --max-group-size."""

    def edge_strength(pair: Pair) -> tuple[int, int, int, int]:
        entry = evidence[pair]
        if EXACT_NAME in entry.reasons:
            tier = 3
        elif FUZZY_NAME in entry.reasons:
            tier = 2
        else:
            tier = 1
        return (-tier, -entry.score, pair[0], pair[1])

    union = UnionFind()
    deferred: list[Pair] = []
    for pair in sorted(evidence, key=edge_strength):
        left, right = pair
        if union.find(left) == union.find(right):
            continue
        if union.size_of(left) + union.size_of(right) > max_group_size:
            deferred.append(pair)
            continue
        union.union(left, right)
    return union, deferred


def describe_group(records: list[dict], entries: list[PairEvidence]) -> dict:
    """One reviewable group: who is in it, why, and how much to trust it."""
    similarities = [entry.score for entry in entries]
    distances = [
        entry.distance_km for entry in entries if entry.distance_km is not None
    ]
    countries = sorted({r["country"] for r in records if r.get("country")})
    sources = sorted({s for r in records for s in r.get("sources") or []})

    group = {
        "resource_ids": [r["id"] for r in records],
        "reasons": sorted({reason for entry in entries for reason in entry.reasons}),
        "signals": {
            "normalized_names": sorted({r["core"] for r in records}),
            "min_name_similarity": min(similarities) if similarities else None,
            "countries": countries,
            "same_country": len(countries) <= 1,
            "max_distance_km": round(max(distances), 2) if distances else None,
            "discriminators": sorted({d for r in records for d in r["discriminators"]}),
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
    return group


def group_rank(group: dict) -> tuple[int, bool, bool, bool, int, int]:
    """Most trustworthy first: exact-key, cross-source, same-country, tightest."""
    signals = group["signals"]
    return (
        CONFIDENCE_ORDER[group["confidence"]],
        EXACT_NAME not in group["reasons"],
        signals["single_source"],
        not signals["same_country"],
        -(signals["min_name_similarity"] or 0),
        len(group["resource_ids"]),
    )


def build_groups(
    prepared: list[dict], edges: list[Edge], max_group_size: int
) -> tuple[list[dict], list[Pair]]:
    """Cluster the surviving edges, then assemble reviewable groups."""
    evidence = collect_evidence(prepared, edges)
    union, deferred = cluster_pairs(evidence, max_group_size)

    groups: list[dict] = []
    for members in union.groups().values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda index: prepared[index]["id"])
        entries: list[PairEvidence] = []
        for left, right in combinations(members, 2):
            entry = evidence.get((min(left, right), max(left, right)))
            if entry is not None:
                entries.append(entry)
        records = [prepared[index] for index in members]
        groups.append(describe_group(records, entries))

    groups.sort(key=group_rank)
    return groups, deferred


def split_by_confidence(
    groups: list[dict], min_confidence: str
) -> tuple[list[dict], Counter]:
    """Partition into the groups worth emitting now and a count of the rest."""
    limit = CONFIDENCE_ORDER[min_confidence]
    kept: list[dict] = []
    withheld: Counter = Counter()
    for group in groups:
        if CONFIDENCE_ORDER[group["confidence"]] <= limit:
            kept.append(group)
        else:
            withheld[group["confidence"]] += 1
    return kept, withheld


def summarize(
    groups: list[dict],
    deferred: list[Pair],
    prepared: list[dict],
    suppressed_keys: list[tuple[str, int]],
    withheld: Counter,
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


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def build_payload(args: argparse.Namespace, groups: list[dict]) -> dict:
    """The groups, carrying the parameters that produced them."""
    return {
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


def main() -> int:
    args = parse_args()

    records = load_records(Path(args.in_path))
    print(f"loaded {len(records)} records", file=sys.stderr)

    prepared = prepare(records, args.location_min_count)

    exact, suppressed_keys = exact_edges(prepared, args.max_key_frequency)
    edges = exact + similarity_edges(
        prepared, args.fuzzy_threshold, args.geo_name_threshold, args.geo_km
    )
    by_reason = Counter(edge.reason for edge in edges)
    print(
        f"edges: exact={by_reason[EXACT_NAME]} fuzzy={by_reason[FUZZY_NAME]} "
        f"geo={by_reason[GEO_PROXIMITY]}",
        file=sys.stderr,
    )

    groups, deferred = build_groups(prepared, edges, args.max_group_size)
    groups, withheld = split_by_confidence(groups, args.min_confidence)
    for position, group in enumerate(groups, start=1):
        group["group_id"] = f"g{position:04d}"

    write_payload(args.out_path, build_payload(args, groups))

    summarize(groups, deferred, prepared, suppressed_keys, withheld)
    print(f"\nwrote {len(groups)} groups to {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
