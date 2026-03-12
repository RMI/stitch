# pyright: reportUnannotatedClassAttribute=false
from collections.abc import Callable
from polyfactory import Require, Use
from polyfactory.decorators import post_generated
from polyfactory.factories.pydantic_factory import ModelFactory


from stitch.ogsi.model import (
    OGFieldResource,
    OGFieldSource,
    OilGasOperator,
    OilGasOwner,
    OilGasFieldBase,
)


EMPTY_OG_FIELD_BASE = OilGasFieldBase(name=None, country=None)
DEFAULT_OG_FIELD_BASE = OilGasFieldBase(name="Default OGFieldBase Name", country="USA")

type ResourceCreateFactory = Callable[..., OGFieldResource]
type SourceFactory = Callable[..., OGFieldSource]


def _construct_str_vals(num: int, attr_: str, parent: str = "OilGasFieldBase"):
    return [f"{parent} {attr_} {i}" for i in range(1, num + 1)]


class OGFieldOperatorFactory(ModelFactory[OilGasOperator]):
    __allow_none_optionals__ = True
    __set_as_default_factory_for_type__ = True

    name = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(3, "name", "OilGasFieldBase.Operator"),
    )

    @classmethod
    def stake(cls) -> float:
        v = ModelFactory.__random__.random() * 100
        return round(v, ndigits=3)


class OGFieldOwnerFactory(ModelFactory[OilGasOwner]):
    __allow_none_optionals__ = True
    __set_as_default_factory_for_type__ = True

    name = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(3, "name", "OilGasFieldBase.Owner"),
    )

    @classmethod
    def stake(cls) -> float:
        v = ModelFactory.__random__.random() * 100
        return round(v, ndigits=3)


class OGFieldBaseFactory(ModelFactory[OilGasFieldBase]):
    __random_seed__ = 1
    __by_name__ = True
    __allow_none_optionals__ = True
    __randomize_collection_length__ = True
    __min_collection_length__ = 0
    __max_collection_length__ = 3
    __set_as_default_factory_for_type__ = True

    name = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(3, "name"),
    )
    country = Use(ModelFactory.__random__.choice, ["USA", "CAN", "RUS", "BRA"])
    name_local = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(2, "name_local"),
    )
    state_province = Use(
        ModelFactory.__random__.choice,
        ["CA", "ON", "Le Favre", "Rio"],
    )
    region = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(3, "region"),
    )
    basin = Use(ModelFactory.__random__.choice, _construct_str_vals(3, "basin"))
    reservoir_formation = Use(
        ModelFactory.__random__.choice,
        _construct_str_vals(3, "reservoir_formation"),
    )


# TODO: move to `utils` make_resource with args for the collection attrs: source_data, constituents, provenance
#  - use the base factory above to build the associated fiels or just None them all
class ResourceFactory(ModelFactory[OGFieldResource]):
    __random_seed__ = 1
    __by_name__ = True
    __allow_none_optionals__ = True
    __randomize_collection_length__ = True
    __min_collection_length__ = 0
    __max_collection_length__ = 5

    source_data = Require()

    @post_generated
    @classmethod
    def repointed_to(cls, id: int | None) -> int | None:
        return None if id is None else cls.__random__.choice([None, 9, 8, 7])

    @post_generated
    @classmethod
    def constituents(cls, id: int | None) -> frozenset[int]:
        if id is None:
            return frozenset()
        length = cls.__random__.randint(0, 5)
        return frozenset(cls.__faker__.random_choices(range(1, id - 1), length=length))

    @post_generated
    @classmethod
    def provenance(cls):
        return {}
