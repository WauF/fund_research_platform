"""Repository functions for the documents table."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.models import Document


def get_by_sha256(session: Session, sha256: str) -> Document | None:
    return session.scalars(select(Document).where(Document.sha256 == sha256)).one_or_none()


def add_document(
    session: Session, *, sha256: str, original_filename: str, size_bytes: int, storage_key: str
) -> tuple[Document, bool]:
    """Insert a document, or return the existing row with the same sha256.

    Returns (document, created). Safe under concurrent uploads of the same file: the unique
    constraint on sha256 decides the winner and the loser gets the winner's row.
    """
    if existing := get_by_sha256(session, sha256):
        return existing, False
    document = Document(
        sha256=sha256,
        original_filename=original_filename,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )
    session.add(document)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_by_sha256(session, sha256)
        if existing is None:  # The IntegrityError was something else.
            raise
        return existing, False
    session.refresh(document)
    return document, True
