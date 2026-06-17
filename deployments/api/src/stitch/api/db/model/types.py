from sqlalchemy import JSON, BigInteger, Dialect, Float, TypeDecorator
from sqlalchemy.dialects import postgresql, sqlite


PORTABLE_BIGINT = (
    BigInteger()
    .with_variant(postgresql.BIGINT(), "postgresql")
    .with_variant(sqlite.INTEGER(), "sqlite")
)
PORTABLE_JSON = JSON().with_variant(postgresql.JSONB(), "postgresql")
PORTABLE_REAL = (
    Float()
    .with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")
    .with_variant(sqlite.REAL(), "sqlite")
)


class StitchJson(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())
