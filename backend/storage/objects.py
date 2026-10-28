"""S3-compatible object storage (SeaweedFS in docker compose) for the raw PDFs."""

from functools import cache
from typing import BinaryIO

import boto3

from app.config import get_settings


class ObjectStore:
    def __init__(self, client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, key: str, body: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(body, self.bucket, key, ExtraArgs={"ContentType": content_type})


@cache
def get_object_store() -> ObjectStore:
    """FastAPI dependency. boto3 clients are thread-safe, so one is shared."""
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    return ObjectStore(client, settings.s3_bucket)
