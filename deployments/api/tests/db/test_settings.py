"""Tests for settings configuration and URL generation."""

from pathlib import Path

from pydantic import SecretStr

from stitch.api.settings import PostgresConfig, Settings, SqliteConfig


class TestPostgresConfig:
    """Tests for PostgresConfig URL generation."""

    def test_to_url_format(self):
        """Verify PostgreSQL URL contains correct driver and components."""
        config = PostgresConfig(
            host="localhost",
            port=5432,
            database="testdb",
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
            database="testdb",
            user="testuser",
            password=SecretStr("secret123"),
        )

        url = config.to_url()

        assert url.password == "secret123"

    def test_defaults(self):
        """Verify default values are applied."""
        config = PostgresConfig()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "postgres"
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


class TestSettings:
    """Tests for Settings dialect switching."""

    def test_get_database_url_postgres_dialect(self, monkeypatch):
        """Dialect=postgresql returns PostgresConfig URL."""
        monkeypatch.setenv("POSTGRES_HOST", "pghost")
        monkeypatch.setenv("POSTGRES_DATABASE", "pgdb")

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
