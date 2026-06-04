from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import URL

from stitch.api import alembic as api_alembic


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
    monkeypatch.setattr(api_alembic, "ApiSettings", DummySettings)

    url = api_alembic.build_db_url()

    assert url == expected.render_as_string(hide_password=False)


def test_run_upgrade_uses_shared_connection_for_alembic(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    monkeypatch.setattr(api_alembic, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(api_alembic, "wait_for_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_alembic, "setup_logging", lambda: None)
    monkeypatch.setattr(api_alembic, "current_revision", lambda conn: "base")
    monkeypatch.setattr(api_alembic, "head_revision", lambda config: "head")

    captured: dict[str, object] = {}

    def fake_upgrade(config, revision):
        captured["revision"] = revision
        captured["connection"] = config.attributes["connection"]

    monkeypatch.setattr(api_alembic.command, "upgrade", fake_upgrade)

    api_alembic.run_upgrade()

    assert captured["revision"] == "head"
    assert captured["connection"] is conn


def test_run_autogenerate_uses_shared_connection_for_alembic(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    monkeypatch.setattr(api_alembic, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(api_alembic, "wait_for_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_alembic, "setup_logging", lambda: None)

    captured: dict[str, object] = {}

    def fake_revision(config, message, autogenerate):
        captured["message"] = message
        captured["autogenerate"] = autogenerate
        captured["connection"] = config.attributes["connection"]

    monkeypatch.setattr(api_alembic.command, "revision", fake_revision)

    api_alembic.run_autogenerate()

    assert captured["message"] == "baseline"
    assert captured["autogenerate"] is True
    assert captured["connection"] is conn


def test_alembic_upgrade_main_uses_cli_revision(monkeypatch):
    captured = {}

    monkeypatch.setattr("sys.argv", ["alembic_upgrade", "base"])
    monkeypatch.setattr(
        "stitch.api.alembic_upgrade.run_upgrade",
        lambda revision: captured.setdefault("revision", revision),
    )

    from stitch.api.alembic_upgrade import main

    main()

    assert captured["revision"] == "base"

def test_run_upgrade_logs_when_already_at_head(monkeypatch, caplog):
    conn = MagicMock()

    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    monkeypatch.setattr(api_alembic, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(api_alembic, "wait_for_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_alembic, "setup_logging", lambda: None)
    monkeypatch.setattr(api_alembic, "current_revision", lambda conn: "head")
    monkeypatch.setattr(api_alembic, "head_revision", lambda config: "head")

    upgrade = MagicMock()
    monkeypatch.setattr(api_alembic.command, "upgrade", upgrade)

    api_alembic.run_upgrade()

    upgrade.assert_not_called()
    assert "database already at Alembic head head; no migrations to run" in caplog.text
