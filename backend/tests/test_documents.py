"""POST /documents: upload + SHA-256 de-duplication.

Runs without Postgres or SeaweedFS: SQLite in memory for the DB and moto's in-process S3 mock
(no sockets). The real stack is covered by the CI docker smoke test.
"""

import hashlib
from collections.abc import Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.main import app
from storage import documents
from storage.db import Base, get_session
from storage.models import Document
from storage.objects import ObjectStore, get_object_store

BUCKET = "documents"


def make_pdf(text: str) -> bytes:
    """Smallest byte string the endpoint accepts as a PDF; content varies with text."""
    return b"%PDF-1.4\n% " + text.encode() + b"\n%%EOF\n"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    # One shared connection: TestClient runs sync endpoints in a worker thread.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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


def upload(client: TestClient, content: bytes, filename: str = "report.pdf"):
    return client.post("/documents", files={"file": (filename, content, "application/pdf")})


def count_documents(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(Document))


def stored_keys(s3) -> list[str]:
    return [obj["Key"] for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])]


def test_upload_stores_pdf_and_creates_record(client, session_factory, s3) -> None:
    pdf = make_pdf("irf-2026-09")

    response = upload(client, pdf)

    assert response.status_code == 201
    body = response.json()
    sha256 = hashlib.sha256(pdf).hexdigest()
    assert body["sha256"] == sha256
    assert body["size_bytes"] == len(pdf)
    assert body["original_filename"] == "report.pdf"
    assert body["storage_key"] == f"pdfs/{sha256}.pdf"
    assert s3.get_object(Bucket=BUCKET, Key=body["storage_key"])["Body"].read() == pdf
    assert count_documents(session_factory) == 1


def test_same_pdf_twice_gives_one_record(client, session_factory, s3) -> None:
    pdf = make_pdf("irf-2026-09")

    first = upload(client, pdf, "IRF_Eylul.pdf")
    # Same bytes under another name is still the same document.
    second = upload(client, pdf, "copy.pdf")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count_documents(session_factory) == 1
    assert len(stored_keys(s3)) == 1


def test_different_pdfs_give_separate_records(client, session_factory, s3) -> None:
    a = upload(client, make_pdf("irf"))
    b = upload(client, make_pdf("tji"))

    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]
    assert count_documents(session_factory) == 2
    assert len(stored_keys(s3)) == 2


def test_non_pdf_is_rejected(client, session_factory, s3) -> None:
    response = upload(client, b"hello, not a pdf", "notes.pdf")

    assert response.status_code == 415
    assert count_documents(session_factory) == 0
    assert stored_keys(s3) == []


def test_too_large_pdf_is_rejected(client, session_factory, s3) -> None:
    # max_upload_mb=1 in the client fixture.
    response = upload(client, make_pdf("x" * (1024 * 1024)))

    assert response.status_code == 413
    assert count_documents(session_factory) == 0
    assert stored_keys(s3) == []


def test_add_document_returns_existing_row_on_race(session_factory, monkeypatch) -> None:
    """Two uploads both miss the lookup; the losing insert must return the winner's row."""
    fields = {
        "sha256": "a" * 64,
        "original_filename": "a.pdf",
        "size_bytes": 1,
        "storage_key": f"pdfs/{'a' * 64}.pdf",
    }
    with session_factory() as session:
        winner, created = documents.add_document(session, **fields)
        assert created

    # The loser's pre-insert lookup ran before the winner committed, so it saw nothing.
    real_lookup = documents.get_by_sha256
    calls = iter([None])
    monkeypatch.setattr(documents, "get_by_sha256", lambda *args: next(calls, real_lookup(*args)))

    with session_factory() as session:
        loser, created = documents.add_document(session, **fields)

    assert not created
    assert loser.id == winner.id
    assert count_documents(session_factory) == 1
