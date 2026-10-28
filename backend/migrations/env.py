"""Alembic environment. Online mode only: migrations always run against a live database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import storage.models  # noqa: F401  (registers tables on Base.metadata for autogenerate)
from app.config import get_settings
from storage.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations() -> None:
    # Tests pass their own connection; otherwise connect with the app's settings.
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
