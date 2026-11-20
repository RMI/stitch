"""Every route is wired to exactly the permissions it should require."""

import inspect

from fastapi.dependencies.models import Dependant

from stitch.api.auth.permissions import (
    MERGE_CANDIDATE_CREATE as MC_CREATE,
    MERGE_CANDIDATE_READ as MC_READ,
    MERGE_CANDIDATE_REVIEW as MC_REVIEW,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_ANY,
    SOURCE_READ_PERMISSIONS,
    SOURCE_WRITE,
)
from stitch.api.routers import auth, health, oil_gas_field_sources, oil_gas_fields

PUBLIC = None

EXPECTED: dict[tuple[str, str], frozenset[str] | None] = {
    ("GET", "/health"): PUBLIC,
    ("GET", "/health/details"): PUBLIC,
    ("GET", "/auth/me"): frozenset(),
    ("GET", "/oil-gas-fields/"): {RESOURCE_READ},
    ("POST", "/oil-gas-fields/"): {RESOURCE_WRITE},
    ("GET", "/oil-gas-fields/filter-options"): frozenset(),
    ("GET", "/oil-gas-fields/merge-candidates"): {MC_READ},
    ("POST", "/oil-gas-fields/merge-candidates"): {MC_CREATE},
    ("GET", "/oil-gas-fields/merge-candidates/{id}"): {MC_READ},
    ("POST", "/oil-gas-fields/merge-candidates/link-all"): {MC_CREATE},
    ("POST", "/oil-gas-fields/merge-candidates/{id}/approve"): {MC_REVIEW},
    ("POST", "/oil-gas-fields/merge-candidates/{id}/deny"): {MC_REVIEW},
    ("GET", "/oil-gas-fields/{id}"): {RESOURCE_READ},
    ("GET", "/oil-gas-fields/{id}/detail"): {RESOURCE_READ},
    ("GET", "/oil-gas-fields/{id}/fields/{field}/sources"): {RESOURCE_READ},
    ("PUT", "/oil-gas-fields/{id}/fields/{field}/sources/priority"): {
        RESOURCE_WRITE,
        *SOURCE_READ_PERMISSIONS,
    },
    ("POST", "/oil-gas-fields/{id}/sources"): {RESOURCE_WRITE, SOURCE_WRITE},
    ("POST", "/oil-gas-field-sources/"): {SOURCE_WRITE},
    ("GET", "/oil-gas-field-sources/"): {SOURCE_READ_ANY},
    ("GET", "/oil-gas-field-sources/{id}"): {SOURCE_READ_ANY},
    ("GET", "/oil-gas-field-sources/{id}/detail"): {SOURCE_READ_ANY},
}


def _required_permissions(dependant: Dependant) -> frozenset[str] | None:
    for sub in dependant.dependencies:
        if getattr(sub.call, "__qualname__", "") == "require_auth.<locals>.dependency":
            return frozenset(inspect.getclosurevars(sub.call).nonlocals["permissions"])
        found = _required_permissions(sub)
        if found is not None:
            return found
    return None


def test_every_route_requires_its_expected_permissions():
    actual = {
        (method, route.path_format): _required_permissions(route.dependant)
        for module in (auth, health, oil_gas_fields, oil_gas_field_sources)
        for route in module.router.routes
        for method in route.methods
    }
    expected = {key: None if v is None else frozenset(v) for key, v in EXPECTED.items()}
    assert actual == expected
