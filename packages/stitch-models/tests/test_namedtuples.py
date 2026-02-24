"""Category C: SourceRef & ConstituentProvenance tests."""

from __future__ import annotations

from stitch.models import ConstituentProvenance, SourceRef


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


def test_constituent_provenance():
    ref = SourceRef("foo", 1)
    prov = ConstituentProvenance(id=1, source_refs=[ref])

    # field access
    assert prov.id == 1
    assert prov.source_refs == [ref]

    # is a tuple + unpacking
    assert isinstance(prov, tuple)
    id_, source_refs = prov
    assert id_ == 1
    assert source_refs == [ref]

    # multiple source refs
    refs = [SourceRef("foo", 1), SourceRef("bar", "abc")]
    prov2 = ConstituentProvenance(id=1, source_refs=refs)
    assert len(prov2.source_refs) == 2
    assert prov2.source_refs[0].source == "foo"
    assert prov2.source_refs[1].source == "bar"
