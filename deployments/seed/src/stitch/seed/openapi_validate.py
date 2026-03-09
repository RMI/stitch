from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from jsonschema import Draft202012Validator


logger = logging.getLogger("stitch.seed")


def _default_openapi_url(api_base_url: str) -> str:
    """
    Best-effort: derive openapi.json from API_BASE_URL.
    If API_BASE_URL is http://api:8000/api/v1 -> http://api:8000/openapi.json
    """
    u = urlparse(api_base_url)
    # strip any path (we want just scheme://host[:port])
    root = u._replace(path="", params="", query="", fragment="")
    return urlunparse(root) + "/openapi.json"



def _resolve_seed_post_path(api_base_url: str) -> str:
    """
    We POST to {API_BASE_URL}/oil-gas-fields/ .
    Convert that into an OpenAPI path key (just the path portion).
    """
    u = urlparse(api_base_url.rstrip("/") + "/oil-gas-fields/")
    return u.path


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

class OpenAPIRequestValidator:
    def __init__(self, api_base_url: str, openapi_url: str | None = None) -> None:
        self._api_base_url = api_base_url
        self._openapi_url = openapi_url or _default_openapi_url(api_base_url)
        self._openapi: dict[str, Any] | None = None
        self._schema: dict[str, Any] | None = None
        self._path: str | None = None
        self._validator: Draft202012Validator | None = None

    def _load(self, client: httpx.Client) -> None:
        if self._validator is not None:
            return

        logger.info("Fetching OpenAPI spec: %s", self._openapi_url)
        resp = client.get(self._openapi_url)
        resp.raise_for_status()
        self._openapi = resp.json()
        if self._openapi is None:
            raise RuntimeError("Cannot find openapi json")

        path = _resolve_seed_post_path(self._api_base_url)
        raw_schema = _extract_post_request_schema(self._openapi, path)
        schema = _dereference(raw_schema, self._openapi, seen=set())

        self._path = path
        self._schema = schema
        self._validator = Draft202012Validator(schema)
        logger.info("Using OpenAPI request schema for POST %s", path)

    def validate(self, payload: dict[str, Any], client: httpx.Client) -> None:
        self._load(client)
        assert self._validator is not None

        errors = sorted(self._validator.iter_errors(payload), key=lambda e: list(e.path))
        if not errors:
            return

        lines: list[str] = []
        for e in errors[:3]:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            lines.append(f"- {loc}: {e.message}")

        message = "OpenAPI validation failed:\n" + "\n".join(lines)
        logger.error(message)
        raise RuntimeError(message)
