import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from jsonschema import Draft202012Validator


_OPENAPI_CACHE: dict[str, Any] | None = None
_REQUEST_SCHEMA_CACHE: dict[str, Any] | None = None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[seed] WARN: {name}={raw!r} is not an int; using {default}")
        return default


# extract JSON schema from open api spec
def _json_pointer_get(doc: dict[str, Any], pointer: str) -> Any:
    # pointer like "#/components/schemas/Foo"
    if not pointer.startswith("#/"):
        raise RuntimeError(f"[seed] only internal refs supported, got: {pointer!r}")
    parts = pointer[2:].split("/")
    cur: Any = doc
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(cur, dict) or part not in cur:
            raise RuntimeError(f"[seed] bad $ref {pointer!r} at {part!r}")
        cur = cur[part]
    return cur


def _dereference(schema: Any, openapi: dict[str, Any], seen: set[str]) -> Any:
    # Walk schema; replace {"$ref": "#/..."} with the referenced object (recursively).
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in seen:
                # avoid infinite loops; return as-is (rare for our components)
                return schema
            seen.add(ref)
            target = _json_pointer_get(openapi, ref)
            target = _dereference(target, openapi, seen)

            # If there are sibling keys alongside $ref, overlay them per JSON Schema behavior.
            if len(schema) > 1:
                merged = dict(target) if isinstance(target, dict) else {"_ref_target": target}
                for k, v in schema.items():
                    if k != "$ref":
                        merged[k] = _dereference(v, openapi, seen)
                return merged
            return target

        return {k: _dereference(v, openapi, seen) for k, v in schema.items()}

    if isinstance(schema, list):
        return [_dereference(v, openapi, seen) for v in schema]

    return schema


def _default_openapi_url(api_base_url: str) -> str:
    """
    Best-effort: derive openapi.json from API_BASE_URL.
    If API_BASE_URL is http://api:8000/api/v1 -> http://api:8000/openapi.json
    """
    u = urlparse(api_base_url)
    # strip any path (we want just scheme://host[:port])
    root = u._replace(path="", params="", query="", fragment="")
    return urlunparse(root) + "/openapi.json"


def _fetch_openapi(client: httpx.Client, openapi_url: str) -> dict[str, Any]:
    global _OPENAPI_CACHE
    if _OPENAPI_CACHE is not None:
        return _OPENAPI_CACHE

    print(f"[seed] fetching OpenAPI spec: {openapi_url}")
    resp = client.get(openapi_url)
    resp.raise_for_status()
    _OPENAPI_CACHE = resp.json()
    return _OPENAPI_CACHE


def _extract_post_request_schema(
    openapi: dict[str, Any],
    path: str,
    method: str = "post",
    content_type: str = "application/json",
) -> dict[str, Any]:
    paths = openapi.get("paths", {})
    if path not in paths:
        raise RuntimeError(
            f"[seed] OpenAPI does not contain path {path!r}. "
            f"Available example keys: {list(paths.keys())[:8]}"
        )
    op = paths[path].get(method)
    if not op:
        raise RuntimeError(f"[seed] OpenAPI has no {method.upper()} operation for {path!r}")

    rb = op.get("requestBody") or {}
    content = (rb.get("content") or {}).get(content_type) or {}
    schema = content.get("schema")
    if not schema:
        raise RuntimeError(
            f"[seed] OpenAPI missing requestBody.content[{content_type!r}].schema for {method.upper()} {path}"
        )
    return schema


def _resolve_seed_post_path(api_base_url: str) -> str:
    """
    We POST to {API_BASE_URL}/oil-gas-fields/ .
    Convert that into an OpenAPI path key (just the path portion).
    """
    u = urlparse(api_base_url.rstrip("/") + "/oil-gas-fields/")
    return u.path


def _validate_against_openapi(payload: dict[str, Any], client: httpx.Client, api_base_url: str) -> None:
    global _REQUEST_SCHEMA_CACHE

    openapi_url = os.getenv("OPENAPI_URL") or _default_openapi_url(api_base_url)
    openapi = _fetch_openapi(client, openapi_url)

    if _REQUEST_SCHEMA_CACHE is None:
        path = _resolve_seed_post_path(api_base_url)
        schema = _extract_post_request_schema(openapi, path)
        # Use OpenAPI doc as referrer so "#/components/..." refs resolve.
        resolved = _dereference(schema, openapi, seen=set())
        _REQUEST_SCHEMA_CACHE = {"schema": resolved, "path": path}

        print(f"[seed] using OpenAPI request schema for POST {path}")

    schema = _REQUEST_SCHEMA_CACHE["schema"]
    validator = Draft202012Validator(schema)

    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        # show first error, plus a couple extras
        lines = []
        for e in errors[:3]:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            lines.append(f"- {loc}: {e.message}")
        raise RuntimeError(
            "[seed] OpenAPI validation failed:\n" + "\n".join(lines)
        )


def build_og_field() -> dict[str, Any]:
    return {
        "name": "turquoise 1080p hard drive",
        "country": "XPG",
        "latitude": 70.0823,
        "longitude": -138.7758,
        "name_local": "Aufderhar LLC 516",
        "state_province": "Tromp, Romaguera and Macejkovic 42",
        "region": "McGlynn - Russel 194",
        "basin": "Wolf LLC 878",
        "owners": None,
        "operators": None,
        "location_type": "Offshore",
        "production_conventionality": "Mixed",
        "primary_hydrocarbon_group": "Light Oil",
        "reservoir_formation": "Lueilwitz, Haag and Strosin 333",
        "discovery_year": 1801,
        "production_start_year": 1802,
        "fid_year": 1803,
        "field_status": "Producing",
        "source": "gem",
    }


def build_payload(i: int) -> dict[str, Any]:
    """
    PR #32 currently defines POST /oil-gas-fields with body model `Resource`,
    which requires an `id: int` plus optional name/country. We'll send id=0
    and let the server decide what to do with it.
    """
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "id": 0,
        "name": f"seeded-og-field-{now}-{i}",
        "country": None,
        "source_data": [build_og_field()],
        "constituents": [],
    }


def post_once(client: httpx.Client, base_url: str, i: int) -> None:
    url = f"{base_url.rstrip('/')}/oil-gas-fields/"
    payload = build_payload(i)
    _validate_against_openapi(payload, client, base_url)
    print(f"[seed] POST {url}")
    print(f"[seed] payload={json.dumps(payload, ensure_ascii=False)}")

    resp = client.post(url, json=payload)
    print(f"[seed] status={resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    print(
        f"[seed] response={json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else body}"
    )

    resp.raise_for_status()


def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
    post_count = _env_int("POST_COUNT", 5)
    timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))

    print("[seed] starting")
    print(f"[seed] API_BASE_URL={base_url}")

    with httpx.Client(timeout=timeout_seconds) as client:
        for i in range(1, post_count + 1):
            post_once(client, base_url, i)

    print("[seed] done")


if __name__ == "__main__":
    main()
