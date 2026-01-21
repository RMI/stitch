"""Tests for settings configuration and URL generation."""

from pathlib import Path

import pytest
from pydantic import SecretStr, TypeAdapter, ValidationError

from stitch.api.settings import OriginUrl, PostgresConfig, Settings, SqliteConfig


class TestPostgresConfig:
    """Tests for PostgresConfig URL generation."""

    def test_to_url_format(self):
        """Verify PostgreSQL URL contains correct driver and components."""
        config = PostgresConfig(
            host="localhost",
            port=5432,
            db="testdb",
            user="testuser",
            password=SecretStr("testpass"),
        )

        url = config.to_url()

        assert url.drivername == "postgresql+psycopg"
        assert url.host == "localhost"
        assert url.port == 5432
        assert url.database == "testdb"
        assert url.username == "testuser"

    def test_to_url_uses_secret_password(self):
        """Verify password is extracted from SecretStr."""
        config = PostgresConfig(
            host="localhost",
            port=5432,
            db="testdb",
            user="testuser",
            password=SecretStr("secret123"),
        )

        url = config.to_url()

        assert url.password == "secret123"

    def test_defaults(self, monkeypatch):
        """Verify default values are applied when env vars are unset."""
        monkeypatch.setenv("POSTGRES_DB", "postgres")
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("POSTGRES_USER", "postgres")
        config = PostgresConfig()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.db == "postgres"
        assert config.user == "postgres"


class TestSqliteConfig:
    """Tests for SqliteConfig URL generation."""

    def test_to_url_memory(self):
        """Verify in-memory SQLite URL when db_path is None."""
        config = SqliteConfig(db_path=None)

        url = config.to_url()

        assert url.drivername == "sqlite+aiosqlite"
        assert url.database == ":memory:"

    def test_to_url_file(self, tmp_path: Path):
        """Verify file-based SQLite URL with path."""
        db_file = tmp_path / "test.db"
        config = SqliteConfig(db_path=db_file)

        url = config.to_url()

        assert url.drivername == "sqlite+aiosqlite"
        assert url.database == str(db_file)


class TestOriginUrlValidation:
    """Tests for OriginUrl type validation."""

    def test_valid_origin_url(self):
        """Valid origin without path/query/fragment passes."""
        adapter = TypeAdapter(OriginUrl)

        result = adapter.validate_python("http://localhost:3000")

        assert str(result) == "http://localhost:3000/"

    def test_valid_origin_url_with_trailing_slash(self):
        """Origin with "/" path passes."""
        adapter = TypeAdapter(OriginUrl)

        result = adapter.validate_python("http://localhost:3000/")

        assert str(result) == "http://localhost:3000/"

    def test_rejects_url_with_path(self):
        """URL with path raises ValueError."""
        adapter = TypeAdapter(OriginUrl)

        with pytest.raises(ValidationError, match="URL must be an origin with no path"):
            adapter.validate_python("http://localhost:3000/api/v1")

    def test_rejects_url_with_query_string(self):
        """URL with query raises ValueError."""
        adapter = TypeAdapter(OriginUrl)

        with pytest.raises(
            ValidationError, match="URL must be an origin with no query string"
        ):
            adapter.validate_python("http://localhost:3000?foo=bar")

    def test_rejects_url_with_fragment(self):
        """URL with fragment raises ValueError."""
        adapter = TypeAdapter(OriginUrl)

        with pytest.raises(
            ValidationError, match="URL must be an origin with no fragment"
        ):
            adapter.validate_python("http://localhost:3000#section")


class TestSettings:
    """Tests for Settings dialect switching."""

    def test_get_database_url_postgres_dialect(self, monkeypatch):
        """Dialect=postgresql returns PostgresConfig URL."""
        monkeypatch.setenv("POSTGRES_HOST", "pghost")
        monkeypatch.setenv("POSTGRES_DB", "pgdb")

        settings = Settings(dialect="postgresql")
        url = settings.get_database_url()

        assert url.drivername == "postgresql+psycopg"
        assert url.host == "pghost"
        assert url.database == "pgdb"

    def test_get_database_url_sqlite_dialect(self):
        """Dialect=sqlite returns SqliteConfig URL."""
        settings = Settings(dialect="sqlite")

        url = settings.get_database_url()

        assert url.drivername == "sqlite+aiosqlite"
        assert url.database == ":memory:"

    def test_default_dialect_is_postgresql(self):
        """Verify default dialect is postgresql."""
        settings = Settings()

        assert settings.dialect == "postgresql"

    def test_default_environment_is_dev(self):
        """Verify default environment is dev."""
        settings = Settings()

        assert settings.environment.value == "dev"

    def test_default_frontend_origin_url(self, monkeypatch):
        """Verify default frontend origin URL is http://localhost:3000."""
        monkeypatch.delenv("FRONTEND_ORIGIN_URL", raising=False)
        settings = Settings(_env_file=None)

        assert str(settings.frontend_origin_url) == "http://localhost:3000/"
