from sqlalchemy import JSON, BigInteger, Dialect, Float, TypeDecorator
from sqlalchemy.dialects import postgresql, sqlite


PORTABLE_BIGINT = (
    BigInteger()
    .with_variant(postgresql.BIGINT(), "postgresql")
    .with_variant(sqlite.INTEGER(), "sqlite")
)
PORTABLE_JSON = JSON().with_variant(postgresql.JSONB(), "postgresql")
PORTABLE_FLOAT = (
    Float()
    .with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")
    .with_variant(sqlite.REAL(), "sqlite")
)

# JSON column where a Python ``None`` binds to SQL NULL (not the JSON ``null``
# literal). Needed so the long values table's "exactly one column populated"
# check sees an unset value column as truly NULL.
PORTABLE_JSON_NULL = JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


class StitchJson(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())
