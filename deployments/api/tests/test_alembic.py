from __future__ import annotations

from sqlalchemy import URL

from stitch.api import alembic_support


def test_build_db_url_uses_app_settings_sync_url(monkeypatch):
    expected = URL.create(
        drivername="postgresql+psycopg",
        username="stitch_migrator",
        password="secret",
        host="db",
        port=5432,
        database="stitch",
    )

    class DummySettings:
        def get_sync_database_url(self):
            return expected

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(alembic_support, "ApiSettings", DummySettings)

    url = alembic_support.build_database_url()

    assert url == expected.render_as_string(hide_password=False)


def test_build_db_url_normalizes_async_sqlite_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///tmp/test.db")

    url = alembic_support.build_database_url()

    assert url == "sqlite+pysqlite:///tmp/test.db"
