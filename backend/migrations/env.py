"""Alembic environment. Online mode only: migrations always run against a live database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

import storage.models  # noqa: F401  (registers tables on Base.metadata for autogenerate)
from app.config import get_settings
from storage.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations(connection: Connection) -> None:
    # render_as_batch: autogenerate emits op.batch_alter_table, which SQLite (tests) needs for
    # ALTER/DROP COLUMN; on Postgres it runs as plain ALTER TABLE.
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


# Tests pass their own connection; otherwise connect with the app's settings.
if (test_connection := config.attributes.get("connection")) is not None:
    run_migrations(test_connection)
else:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_migrations(connection)
