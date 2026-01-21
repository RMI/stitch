# deployments/api/tests/test_init_job.py
import os
import types
import pytest
from unittest.mock import MagicMock

import sqlalchemy

from stitch.api.db import init_job as ij


# ---------- Settings / enums tests ----------

def test_load_settings_parses_enums(monkeypatch):
    monkeypatch.setenv("STITCH_DB_SCHEMA_MODE", ij.SchemaMode.ASSERT_ONLY.value)
    monkeypatch.setenv("STITCH_DB_SEED_MODE", ij.SeedMode.NEVER.value)
    s = ij.load_settings()
    assert s.schema_mode is ij.SchemaMode.ASSERT_ONLY
    assert s.seed_mode is ij.SeedMode.NEVER

def test_load_settings_invalid_enum_raises(monkeypatch):
    monkeypatch.setenv("STITCH_DB_SCHEMA_MODE", "no-such-mode")
    monkeypatch.setenv("STITCH_DB_SEED_MODE", ij.SeedMode.IF_NEEDED.value)
    with pytest.raises(ValueError):
        ij.load_settings()


# ---------- classify_db_state tests (mock sqlalchemy.inspect) ----------

class DummyInspector:
    def __init__(self, table_names):
        self._names = table_names

    def get_table_names(self, schema="public"):
        return list(self._names)


def test_classify_db_state_empty(monkeypatch):
    # patch the inspect function used by the module under test
    monkeypatch.setattr(ij, "inspect", lambda engine: DummyInspector([]))
    # engine can be anything; classify_db_state will call inspect(engine)
    dummy_engine = object()
    expected = {"users", "resources"}
    state, existing = ij.classify_db_state(dummy_engine, expected)
    assert state == "empty"
    assert existing == set()

def test_classify_db_state_ok(monkeypatch):
    monkeypatch.setattr(ij, "inspect", lambda engine: DummyInspector(["users", "resources", "other"]))
    dummy_engine = object()
    expected = {"users", "resources"}
    state, existing = ij.classify_db_state(dummy_engine, expected)
    assert state == "ok"
    assert "users" in existing and "resources" in existing

def test_classify_db_state_partial(monkeypatch):
    monkeypatch.setattr(ij, "inspect", lambda engine: DummyInspector(["users"]))
    dummy_engine = object()
    expected = {"users", "resources"}
    state, existing = ij.classify_db_state(dummy_engine, expected)
    assert state == "partial_or_mismatch"
    assert "users" in existing


# ---------- seed_already_applied tests (mock engine.connect()) ----------

class DummyConnCtx:
    def __init__(self, first_value):
        self._first_value = first_value

    def __enter__(self):
        conn = MagicMock()
        # mimic result.first() returning a row or None
        result = MagicMock()
        result.first.return_value = (1,) if self._first_value else None
        conn.execute.return_value = result
        return conn

    def __exit__(self, exc_type, exc, tb):
        return False


def make_engine_with_connect_returning(first_value):
    engine = MagicMock()
    engine.connect.return_value = DummyConnCtx(first_value)
    return engine


def test_seed_already_applied_true():
    engine = make_engine_with_connect_returning(True)
    assert ij.seed_already_applied(engine, "dev") is True

def test_seed_already_applied_false():
    engine = make_engine_with_connect_returning(False)
    assert ij.seed_already_applied(engine, "dev") is False


# ---------- advisory lock tests (mock connection) ----------

def test_acquire_release_lock_calls_execute():
    # create a mock connection (not engine) that has execute
    conn = MagicMock()
    ij.acquire_lock(conn)
    conn.execute.assert_called()
    # The SQL should reference pg_advisory_lock or pg_try_advisory_lock with hashtext
    sql_text = str(conn.execute.call_args[0][0])
    assert "pg_advisory_lock" in sql_text or "pg_try_advisory_lock" in sql_text

    # release
    conn.reset_mock()
    ij.release_lock(conn)
    conn.execute.assert_called()
    sql_text = str(conn.execute.call_args[0][0])
    assert "pg_advisory_unlock" in sql_text or "pg_try_advisory_unlock" in sql_text

