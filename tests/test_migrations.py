"""slim-prep's migrations: reversible, matching the models, and kept to slim-prep's own tables."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from slim_prep.persistence import (
    migrate,
    tables,  # noqa: F401  (registers the tables on Base)
)
from slim_prep.persistence.db import Base

HEAD = "0002"


def _version(connection) -> str | None:
    return MigrationContext.configure(
        connection, opts={"version_table": migrate.VERSION_TABLE}
    ).get_current_revision()


def test_upgrade_downgrade_upgrade(engine):
    with engine.begin() as connection:
        migrate.upgrade(connection)
        assert _version(connection) == HEAD
        migrate.downgrade(connection)
        assert _version(connection) is None
        migrate.upgrade(connection)
        assert _version(connection) == HEAD
        migrate.downgrade(connection)


def test_uses_its_own_version_table_and_leaves_other_modules_alone(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version_slim_data (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version_slim_data VALUES ('slim_data_rev')"))
        connection.execute(text("CREATE TABLE tr_submissions (id INTEGER PRIMARY KEY)"))
        try:
            migrate.upgrade(connection)
            names = set(inspect(connection).get_table_names())
            assert migrate.VERSION_TABLE in names
            assert {"alembic_version_slim_data", "tr_submissions"} <= names
            assert connection.execute(text("SELECT version_num FROM alembic_version_slim_data")).scalar() == (
                "slim_data_rev"
            )
        finally:
            migrate.downgrade(connection)
            connection.execute(text("DROP TABLE alembic_version_slim_data"))
            connection.execute(text("DROP TABLE tr_submissions"))
            connection.execute(text(f"DROP TABLE {migrate.VERSION_TABLE}"))


def test_models_match_migrations(engine):
    with engine.begin() as connection:
        migrate.upgrade(connection)
        try:
            context = MigrationContext.configure(
                connection,
                opts={
                    "version_table": migrate.VERSION_TABLE,
                    "include_object": lambda obj, name, type_, *_: (
                        type_ != "table" or name in Base.metadata.tables
                    ),
                },
            )
            assert compare_metadata(context, Base.metadata) == []
        finally:
            migrate.downgrade(connection)
