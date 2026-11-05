"""Shared fixtures: the API against SQLite in memory and moto's in-process S3 mock (no sockets).

The real stack (Postgres + SeaweedFS) is covered by the CI docker smoke test.
"""

from collections.abc import Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.main import app
from storage.db import Base, get_session
from storage.objects import ObjectStore, get_object_store

BUCKET = "documents"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    # One shared connection: TestClient runs sync endpoints in a worker thread.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # SQLite ignores foreign keys unless asked; Postgres always enforces them.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def s3() -> Iterator:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def client(session_factory: sessionmaker[Session], s3) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_object_store] = lambda: ObjectStore(s3, BUCKET)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, max_upload_mb=1)
    yield TestClient(app)
    app.dependency_overrides.clear()
