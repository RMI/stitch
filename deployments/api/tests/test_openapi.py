# Check that the open api schema generates sucessfully (fails if Self is used).
def test_openapi_schema_generates():
    from stitch.api.main import app

    schema = app.openapi()  # should not raise
    assert schema["openapi"].startswith("3.")
    assert "paths" in schema and schema["paths"]  # sanity check: not empty


def _resolve_component_schema(schema: dict, schema_ref: dict) -> dict:
    ref = schema_ref["$ref"]
    _, _, component_path = ref.partition("#/")
    resolved = schema
    for part in component_path.split("/"):
        resolved = resolved[part]
    return resolved


def test_openapi_exposes_client_library_contract():
    from stitch.api.main import app

    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/health" in paths
    assert "get" in paths["/api/v1/health"]

    assert "/api/v1/oil-gas-fields/" in paths
    list_operation = paths["/api/v1/oil-gas-fields/"]["get"]
    create_operation = paths["/api/v1/oil-gas-fields/"]["post"]

    assert "parameters" in list_operation
    assert create_operation["requestBody"]["content"]["application/json"]["schema"]

    assert "/api/v1/oil-gas-fields/{id}/detail" in paths
    detail_operation = paths["/api/v1/oil-gas-fields/{id}/detail"]["get"]
    assert "/api/v1/oil-gas-field-sources/{id}/detail" in paths
    assert "/api/v1/oil-gas-field-sources/" in paths

    assert "/api/v1/oil-gas-fields/merge-candidates" in paths
    merge_operation = paths["/api/v1/oil-gas-fields/merge-candidates"]["post"]
    assert merge_operation["requestBody"]["content"]["application/json"]["schema"]
    source_create_operation = paths["/api/v1/oil-gas-field-sources/"]["post"]
    source_create_schema = source_create_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    source_create_component = _resolve_component_schema(
        schema, source_create_schema["oneOf"][0]
    )
    assert "source_record" in source_create_component["required"]

    list_schema = list_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    detail_schema = detail_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    list_component = _resolve_component_schema(schema, list_schema)
    detail_component = _resolve_component_schema(schema, detail_schema)

    assert list_component["type"] == "object"
    assert "items" in list_component["properties"]

    assert detail_component["type"] == "object"
    assert {"id", "data"}.issubset(detail_component["properties"])

    # STIT-418: the single-resource read views expose the redirect flag so a
    # client can tell the returned resource is not the one it requested.
    get_operation = paths["/api/v1/oil-gas-fields/{id}"]["get"]
    get_schema = get_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    get_component = _resolve_component_schema(schema, get_schema)
    assert "requested_resource_id" in get_component["properties"]
    assert "requested_resource_id" in detail_component["properties"]
