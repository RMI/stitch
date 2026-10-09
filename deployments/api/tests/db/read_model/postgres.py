"""Opt-in Postgres for the tests SQLite can't exercise.

Set ``STITCH_TEST_POSTGRES_URL`` to a disposable database to run them::

    STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch

Each test builds the tables in its own new schema and drops it afterwards
(``pg_session_factory`` in ``conftest.py``); existing tables are not touched.
"""

import os

import pytest

POSTGRES_URL = os.environ.get("STITCH_TEST_POSTGRES_URL")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="set STITCH_TEST_POSTGRES_URL to run Postgres tests"
)
