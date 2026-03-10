# Check that the open api schema generates sucessfully (fails if Self is used).
def test_openapi_schema_generates():
    from stitch.api.main import app

    schema = app.openapi()  # should not raise
    assert schema["openapi"].startswith("3.")
    assert "paths" in schema and schema["paths"]  # sanity check: not empty
