"""PDF upload API. The SHA-256 of the file content is the identity of a document."""

import hashlib
from datetime import datetime
from typing import Annotated, BinaryIO

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from storage import documents
from storage.db import get_session
from storage.objects import ObjectStore, get_object_store

router = APIRouter(prefix="/documents", tags=["documents"])

PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 1024 * 1024


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sha256: str
    original_filename: str
    size_bytes: int
    storage_key: str
    created_at: datetime


def hash_pdf(stream: BinaryIO, max_bytes: int) -> tuple[str, int]:
    """Validate that the stream is a PDF within the size limit; return (sha256 hex, size)."""
    if stream.read(len(PDF_MAGIC)) != PDF_MAGIC:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a PDF")
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, f"PDF is larger than {max_bytes} bytes"
            )
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest(), size


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": DocumentOut, "description": "Already uploaded"}},
)
def upload_document(
    file: UploadFile,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentOut:
    """Upload a PDF. 201 if new; 200 with the existing record if the same content was seen."""
    sha256, size = hash_pdf(file.file, settings.max_upload_mb * 1024 * 1024)

    if existing := documents.get_by_sha256(session, sha256):
        response.status_code = status.HTTP_200_OK
        return DocumentOut.model_validate(existing)

    # Content-addressed key: a concurrent upload of the same file writes the same object,
    # so the object store never holds duplicates either.
    storage_key = f"pdfs/{sha256}.pdf"
    store.put(storage_key, file.file, "application/pdf")
    document, created = documents.add_document(
        session,
        sha256=sha256,
        original_filename=(file.filename or "document.pdf")[:255],
        size_bytes=size,
        storage_key=storage_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return DocumentOut.model_validate(document)
