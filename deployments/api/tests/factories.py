from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.pytest_plugin import register_fixture

from typing import Any, override

from stitch.ogsi.model import (
    LLMSource,
    OGFieldSource,
    OilGasOperator,
    OilGasOwner,
    RMISource,
    WoodMacSource,
    GemSource,
)
from stitch.ogsi.model.og_field import OilGasFieldBase

from stitch.api.entities import Resource

EMPTY_OG_FIELD_BASE = OilGasFieldBase(name=None, country=None)
DEFAULT_OG_FIELD_BASE = OilGasFieldBase(name="Default OGFieldBase Name", country="USA")


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


@register_fixture(name="og_field_base_factory")
class OGFieldBaseFactory(ModelFactory[OilGasFieldBase]):
    __random_seed__ = 1
    __by_name__ = True
    __allow_none_optionals__ = True

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


def make_source(fact: OGFieldBaseFactory) -> OGFieldSource:
    base = fact.build()
    managed = fact.__random__.random() < 0.5
    source = fact.__random__.choice(["llm", "rmi", "wm", "gem"])
    id_ = fact.__random__.randint(1, 100) if managed else None

    kwargs: dict[str, Any] = {**base.model_dump(), "id": id_}

    match source:
        case "llm":
            return LLMSource(**kwargs)
        case "rmi":
            return RMISource(**kwargs)
        case "wm":
            return WoodMacSource(**kwargs)
        case "gem":
            return GemSource(**kwargs)
    empty_kw = EMPTY_OG_FIELD_BASE.model_dump()
    return GemSource(**empty_kw, id=999)


# class OGFieldSourceFactory(ModelFactory[OGFieldSource]): ...
#
#
class ResourceFactory(ModelFactory[Resource]):
    __by_name__ = True
    __allow_none_optionals__ = True

    @classmethod
    @override
    def get_provider_map(cls) -> dict[type, Any]:
        providers_map = super().get_provider_map()
        og_field_base_fact = OGFieldBaseFactory()
        return {OGFieldSource: lambda: make_source(og_field_base_fact), **providers_map}
