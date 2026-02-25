"""Category C: SourceRef tests."""

from __future__ import annotations

from stitch.models import SourceRef


def test_source_ref_is_a_well_behaved_namedtuple():
    ref = SourceRef("foo", 1)
    assert ref.source == "foo"
    assert ref.id == 1

    # keyword construction gives same result
    assert SourceRef(source="foo", id=1) == ref

    # indexing
    assert ref[0] == "foo"
    assert ref[1] == 1

    # length and unpacking
    assert len(ref) == 2
    source, id_ = ref
    assert source == "foo"
    assert id_ == 1

    # tuple coercion
    assert tuple(ref) == ("foo", 1)


def test_source_ref_equality_and_hashing():
    a = SourceRef("foo", 1)
    b = SourceRef("foo", 1)
    c = SourceRef("bar", 2)

    assert a == b
    assert a != c
    assert hash(a) == hash(b)

    # set deduplication
    refs = {a, SourceRef("foo", 1), c}
    assert len(refs) == 2

    # dict key lookup
    d = {a: "found"}
    assert d[SourceRef("foo", 1)] == "found"

    # equality with plain tuple
    assert a == ("foo", 1)
