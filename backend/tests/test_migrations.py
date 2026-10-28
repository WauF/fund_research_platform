"""Alembic migrations: apply cleanly, roll back cleanly, and match the SQLAlchemy models.

Rules behind these tests: .claude/skills/db-migrations/SKILL.md. CI's docker job repeats the
round trip on real Postgres.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, inspect

from storage.db import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def connection(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    with engine.begin() as connection:
        yield connection
    engine.dispose()


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["connection"] = connection
    return config


def test_single_head() -> None:
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) == 1, f"multiple heads {heads}: renumber your migration's down_revision"


def test_migrations_match_models(connection: Connection) -> None:
    command.upgrade(alembic_config(connection), "head")

    diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == [], "models and migrations differ; run `alembic revision --autogenerate`"


def test_downgrade_round_trip(connection: Connection) -> None:
    """Every downgrade() works and undoes its upgrade(), so upgrading again succeeds."""
    config = alembic_config(connection)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert set(inspect(connection).get_table_names()) <= {"alembic_version"}

    command.upgrade(config, "head")
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
