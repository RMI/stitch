"""Postgres for the tests SQLite can't exercise.

CI runs them against a throwaway Postgres (see ``.github/workflows/python-test.yml``).
Locally they're skipped unless ``STITCH_TEST_POSTGRES_URL`` points at a
disposable database::

    STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch

Each test builds the tables in its own new schema and drops it afterwards
(``pg_session_factory`` in ``conftest.py``); existing tables are not touched.

Setting ``STITCH_REQUIRE_POSTGRES_TESTS`` (as CI does) makes a missing URL an
error instead of a skip, so these tests can't silently stop running.
"""

import os

import pytest

POSTGRES_URL = os.environ.get("STITCH_TEST_POSTGRES_URL")

if os.environ.get("STITCH_REQUIRE_POSTGRES_TESTS") and not POSTGRES_URL:
    raise RuntimeError(
        "STITCH_REQUIRE_POSTGRES_TESTS is set but STITCH_TEST_POSTGRES_URL is not: "
        "the Postgres tests would be skipped."
    )

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="set STITCH_TEST_POSTGRES_URL to run Postgres tests"
)
