"""Alembic migrations apply cleanly and match the SQLAlchemy models (no forgotten migration)."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from storage.db import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_migrations_match_models(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    config = Config(ALEMBIC_INI)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == [], "models and migrations differ; run `alembic revision --autogenerate`"
