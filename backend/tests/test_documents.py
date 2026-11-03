"""/documents: upload + SHA-256 de-duplication, listing and lookup.

Fixtures (SQLite in memory, moto S3 mock): tests/conftest.py.
"""

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from storage import documents
from storage.models import Document
from tests.conftest import BUCKET


def make_pdf(text: str) -> bytes:
    """Smallest byte string the endpoint accepts as a PDF; content varies with text."""
    return b"%PDF-1.4\n% " + text.encode() + b"\n%%EOF\n"


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


def test_list_documents_newest_first_with_paging(client) -> None:
    ids = [upload(client, make_pdf(code)).json()["id"] for code in ("irf", "tji", "tej")]

    page = client.get("/documents", params={"limit": 2})
    rest = client.get("/documents", params={"limit": 2, "offset": 2})

    assert page.status_code == 200
    assert [d["id"] for d in page.json()["items"]] == ids[::-1][:2]
    assert page.json()["total"] == 3
    assert [d["id"] for d in rest.json()["items"]] == ids[:1]


def test_list_documents_rejects_bad_paging(client) -> None:
    assert client.get("/documents", params={"limit": 0}).status_code == 422
    assert client.get("/documents", params={"limit": 201}).status_code == 422
    assert client.get("/documents", params={"offset": -1}).status_code == 422


def test_get_document(client) -> None:
    created = upload(client, make_pdf("irf")).json()

    assert client.get(f"/documents/{created['id']}").json() == created
    assert client.get("/documents/999").status_code == 404
