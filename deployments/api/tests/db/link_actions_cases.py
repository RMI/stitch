"""Parameter tables for ``test_link_actions``, as ``{case id: [records, expected, *extras]}``.

A record is the positional tuple ``(rid, name, country, source, status)``, trailing
fields omittable. ``case`` turns one table entry into the ``State`` under test.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from stitch.ogsi.model import SOURCE_PRIORITY
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.db.model import MembershipStatus
from stitch.api.entities import MergeCandidateStatus

ALL_SOURCES: frozenset[OGSISrcKey] = frozenset(SOURCE_PRIORITY)

Groups = list[tuple[int, ...]]
Candidates = tuple[tuple[MergeCandidateStatus, tuple[int, ...]], ...]
Extra = tuple[str, Any]
Cases = dict[str, list[Any]]


@dataclass(frozen=True)
class Rec:
    """One source record with its value rows and membership; ``None`` writes no value row."""

    rid: int
    name: str | None
    country: str | None
    source: OGSISrcKey = "gem"
    status: MembershipStatus = MembershipStatus.ACTIVE


@dataclass(frozen=True)
class State:
    """The database a case starts from; resources ``1..N`` are implied by ``records`` and ``repointed``."""

    records: tuple[Rec, ...] = ()
    repointed: Mapping[int, int] = field(default_factory=dict)
    candidates: Candidates = ()
    licensed: Collection[OGSISrcKey] = ALL_SOURCES


def repointed(targets: Mapping[int, int]) -> Extra:
    """Repoint resources, given as ``{resource id: target id}``."""
    return ("repointed", targets)


def licensed(*sources: OGSISrcKey) -> Extra:
    """Restrict the caller's licences; no argument licenses nothing."""
    return ("licensed", frozenset(sources))


def _candidates(status: MergeCandidateStatus, id_sets: tuple[tuple[int, ...], ...]):
    return ("candidates", tuple((status, ids) for ids in id_sets))


def denied(*id_sets: tuple[int, ...]) -> Extra:
    """A DENIED merge candidate per id set, in the order given."""
    return _candidates(MergeCandidateStatus.DENIED, id_sets)


def pending(*id_sets: tuple[int, ...]) -> Extra:
    """A PENDING merge candidate per id set, in the order given."""
    return _candidates(MergeCandidateStatus.PENDING, id_sets)


def approved(*id_sets: tuple[int, ...]) -> Extra:
    """An APPROVED merge candidate per id set, in the order given."""
    return _candidates(MergeCandidateStatus.APPROVED, id_sets)


def case(table: Cases, case_id: str, *, as_param: bool = True) -> Any:
    """Return one case as a ``pytest.param``, or as the bare ``(state, expected)`` pair."""
    records, expected, *extras = table[case_id]
    overrides = dict(extras)
    assert len(overrides) == len(extras), f"{case_id}: conflicting state extras"
    state = State(records=tuple(Rec(*rec) for rec in records), **overrides)
    return pytest.param(state, expected, id=case_id) if as_param else (state, expected)


def params(table: Cases) -> list[Any]:
    """Every case in ``table`` as a ``pytest.param``, in table order."""
    return [case(table, case_id) for case_id in table]


TWO_SHARING_A_KEY = ((1, "Troll", "NO"), (2, "Troll", "NO"))
THREE_SHARING_A_KEY = (*TWO_SHARING_A_KEY, (3, "Troll", "NO"))
FOUR_SHARING_A_KEY = (*THREE_SHARING_A_KEY, (4, "Troll", "NO"))

LINKED_ONLY_BY_LOWEST_PRIORITY_SOURCE = (
    (1, "Alpha", "NO", "rmi"),
    (1, "Troll", "NO", "llm"),
    (2, "Troll", "NO", "llm"),
)


KEY_NORMALIZATION: Cases = {
    "identical": [TWO_SHARING_A_KEY, [(1, 2)]],
    "name-case-differs": [[(1, "Troll", "NO"), (2, "troll", "NO")], [(1, 2)]],
    "both-halves-untrimmed": [[(1, "Troll", "NO"), (2, "  troll  ", "no")], [(1, 2)]],
    "non-breaking-space": [[(1, "Troll", "NO"), (2, "\xa0Troll\xa0", "NO")], [(1, 2)]],
    "casefold-sharp-s": [[(1, "Straße", "DE"), (2, "STRASSE", "DE")], [(1, 2)]],
    "country-differs": [[(1, "Troll", "NO"), (2, "Troll", "US")], []],
    "name-blank-after-strip": [[(1, "   ", "NO"), (2, "   ", "NO")], []],
    "country-absent": [[(1, "Troll", None), (2, "Troll", None)], []],
}


MEMBERSHIP_AND_RESOURCE_ELIGIBILITY: Cases = {
    "both-memberships-active": [TWO_SHARING_A_KEY, [(1, 2)]],
    "one-membership-inactive": [
        [(1, "Troll", "NO"), (2, "Troll", "NO", "gem", MembershipStatus.INACTIVE)],
        [],
    ],
    "one-membership-invalid": [
        [(1, "Troll", "NO"), (2, "Troll", "NO", "gem", MembershipStatus.INVALID)],
        [],
    ],
    "repointed-resource-with-active-membership": [
        TWO_SHARING_A_KEY,
        [],
        repointed({2: 1}),
    ],
}


KEY_FROM_ONE_SOURCE_RECORD: Cases = {
    "one-record-carries-name-and-country": [TWO_SHARING_A_KEY, [(1, 2)]],
    "name-and-country-on-different-records": [
        [
            (1, "Troll", None),
            (1, None, "NO"),
            (2, "Troll", None),
            (2, None, "NO"),
        ],
        [],
    ],
    "name-only-record-contributes-nothing": [
        [
            (1, "Troll", None),
            (2, "Troll", "NO"),
            (3, "Troll", "NO"),
        ],
        [(2, 3)],
    ],
    "two-matching-records-on-one-resource-is-no-self-match": [
        [(1, "Troll", "NO"), (1, "Troll", "NO")],
        [],
    ],
}


CHAINING: Cases = {
    "two-keys-chain-into-one-group": [
        [
            (1, "Alpha", "NO"),
            (2, "Alpha", "NO"),
            (2, "Beta", "NO"),
            (3, "Beta", "NO"),
        ],
        [(1, 2, 3)],
    ],
    "unlinked-pairs-stay-separate": [
        [
            (1, "Alpha", "NO"),
            (2, "Alpha", "NO"),
            (3, "Beta", "NO"),
            (4, "Beta", "NO"),
        ],
        [(1, 2), (3, 4)],
    ],
    "three-keys-chain-into-one-group-of-four": [
        [
            (1, "Alpha", "NO"),
            (2, "Alpha", "NO"),
            (2, "Beta", "NO"),
            (3, "Beta", "NO"),
            (3, "Gamma", "NO"),
            (4, "Gamma", "NO"),
        ],
        [(1, 2, 3, 4)],
    ],
}


DENIED_CANDIDATES: Cases = {
    "no-denial": [THREE_SHARING_A_KEY, [(1, 2, 3)]],
    "denied-1-2-keeps-lower-id": [THREE_SHARING_A_KEY, [(1, 3)], denied((1, 2))],
    "denied-2-3-keeps-lower-id": [THREE_SHARING_A_KEY, [(1, 2)], denied((2, 3))],
    "denied-1-2-and-1-3-leaves-one": [THREE_SHARING_A_KEY, [], denied((1, 2), (1, 3))],
    "denied-1-3-then-3-4": [FOUR_SHARING_A_KEY, [(1, 2, 4)], denied((1, 3), (3, 4))],
    "denied-3-4-then-1-3": [FOUR_SHARING_A_KEY, [(1, 2, 4)], denied((3, 4), (1, 3))],
    "denied-set-equals-whole-group": [TWO_SHARING_A_KEY, [], denied((1, 2))],
}


CANDIDATE_STATUS_GATING: Cases = {
    "pending-does-not-suppress": [TWO_SHARING_A_KEY, [(1, 2)], pending((1, 2))],
    "approved-does-not-suppress": [TWO_SHARING_A_KEY, [(1, 2)], approved((1, 2))],
    "denied-suppresses": [TWO_SHARING_A_KEY, [], denied((1, 2))],
}


LICENSED_SOURCES: Cases = {
    "both-records-licensed": [TWO_SHARING_A_KEY, [(1, 2)], licensed("gem")],
    "one-record-unlicensed": [
        [(1, "Troll", "NO"), (2, "Troll", "NO", "rmi")],
        [],
        licensed("gem"),
    ],
    "both-sources-licensed": [
        [(1, "Troll", "NO"), (2, "Troll", "NO", "rmi")],
        [(1, 2)],
        licensed("gem", "rmi"),
    ],
    "links-through-lowest-priority-source": [
        LINKED_ONLY_BY_LOWEST_PRIORITY_SOURCE,
        [(1, 2)],
    ],
    "licensing-out-the-linking-record-breaks-the-group": [
        LINKED_ONLY_BY_LOWEST_PRIORITY_SOURCE,
        [],
        licensed("rmi"),
    ],
    "licensing-only-the-linking-record-keeps-the-group": [
        LINKED_ONLY_BY_LOWEST_PRIORITY_SOURCE,
        [(1, 2)],
        licensed("llm"),
    ],
    "nothing-licensed": [TWO_SHARING_A_KEY, [], licensed()],
}


RESULT_SHAPE_AND_ORDERING: Cases = {
    "interleaved-groups-sorted-by-first-id-not-discovery-order": [
        [
            (2, "Zulu", "NO"),
            (3, "Zulu", "NO"),
            (1, "Alpha", "NO"),
            (4, "Alpha", "NO"),
        ],
        [(1, 4), (2, 3)],
    ],
    "spike-link-scope-md-fixed-example": [
        [
            (1, "Troll", "NO"),
            (2, "  troll  ", "no"),
            (3, "Troll", "NO"),
            (4, "Ekofisk", "NO"),
            (5, "Ekofisk", "NO"),
            (6, "Ekofisk", "US"),
            (7, "Statfjord", "NO"),
            (7, "Troll", "NO"),
            (8, None, "NO"),
        ],
        [(1, 2, 7)],
        repointed({5: 4}),
        denied((1, 3)),
    ],
    "no-shared-keys": [
        [
            (1, "Alpha", "NO"),
            (2, "Beta", "NO"),
            (3, "Gamma", "NO"),
        ],
        [],
    ],
    "one-shared-key": [
        [
            (1, "Alpha", "NO"),
            (2, "Beta", "NO"),
            (3, "Alpha", "NO"),
        ],
        [(1, 3)],
    ],
}


TABLES: dict[str, Cases] = {
    "key-normalization": KEY_NORMALIZATION,
    "membership-and-resource-eligibility": MEMBERSHIP_AND_RESOURCE_ELIGIBILITY,
    "key-from-one-source-record": KEY_FROM_ONE_SOURCE_RECORD,
    "chaining": CHAINING,
    "denied-candidates": DENIED_CANDIDATES,
    "candidate-status-gating": CANDIDATE_STATUS_GATING,
    "licensed-sources": LICENSED_SOURCES,
    "result-shape-and-ordering": RESULT_SHAPE_AND_ORDERING,
}

ALL_CASES: Cases = {
    f"{group}/{case_id}": entry
    for group, table in TABLES.items()
    for case_id, entry in table.items()
}
