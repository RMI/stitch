"""Category C: SourceRef & ConstituentProvenance tests."""

from __future__ import annotations

from stitch.models import ConstituentProvenance, SourceRef


# ---------------------------------------------------------------------------
# SourceRef construction
# ---------------------------------------------------------------------------


class TestSourceRefConstruction:
    def test_positional_construction(self):
        ref = SourceRef("foo", 1)
        assert ref.source == "foo"
        assert ref.id == 1

    def test_keyword_construction(self):
        ref = SourceRef(source="foo", id=1)
        assert ref.source == "foo"
        assert ref.id == 1

    def test_tuple_unpacking(self):
        ref = SourceRef("foo", 1)
        source, id_ = ref
        assert source == "foo"
        assert id_ == 1

    def test_index_access(self):
        ref = SourceRef("foo", 1)
        assert ref[0] == "foo"
        assert ref[1] == 1

    def test_length(self):
        ref = SourceRef("foo", 1)
        assert len(ref) == 2

    def test_tuple_coercion(self):
        ref = SourceRef("foo", 1)
        assert tuple(ref) == ("foo", 1)


# ---------------------------------------------------------------------------
# SourceRef hashability
# ---------------------------------------------------------------------------


class TestSourceRefHashability:
    def test_equal_refs_are_equal(self):
        a = SourceRef("foo", 1)
        b = SourceRef("foo", 1)
        assert a == b

    def test_different_refs_are_unequal(self):
        a = SourceRef("foo", 1)
        b = SourceRef("bar", 2)
        assert a != b

    def test_same_hash_for_equal_refs(self):
        a = SourceRef("foo", 1)
        b = SourceRef("foo", 1)
        assert hash(a) == hash(b)

    def test_set_deduplication(self):
        refs = {SourceRef("foo", 1), SourceRef("foo", 1), SourceRef("bar", 2)}
        assert len(refs) == 2

    def test_dict_key_behavior(self):
        d = {SourceRef("foo", 1): "found"}
        assert d[SourceRef("foo", 1)] == "found"

    def test_equality_with_plain_tuple(self):
        ref = SourceRef("foo", 1)
        assert ref == ("foo", 1)


# ---------------------------------------------------------------------------
# ConstituentProvenance
# ---------------------------------------------------------------------------


class TestConstituentProvenance:
    def test_construction_and_field_access(self):
        ref = SourceRef("foo", 1)
        prov = ConstituentProvenance(id=1, source_refs=[ref])
        assert prov.id == 1
        assert prov.source_refs == [ref]

    def test_multiple_source_refs(self):
        refs = [SourceRef("foo", 1), SourceRef("bar", "abc")]
        prov = ConstituentProvenance(id=1, source_refs=refs)
        assert len(prov.source_refs) == 2
        assert prov.source_refs[0].source == "foo"
        assert prov.source_refs[1].source == "bar"

    def test_tuple_unpacking(self):
        ref = SourceRef("foo", 1)
        prov = ConstituentProvenance(id=1, source_refs=[ref])
        id_, source_refs = prov
        assert id_ == 1
        assert source_refs == [ref]

    def test_is_a_tuple(self):
        ref = SourceRef("foo", 1)
        prov = ConstituentProvenance(id=1, source_refs=[ref])
        assert isinstance(prov, tuple)
