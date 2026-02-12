from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from google.cloud import storage
from app.core.config import settings


@lru_cache(maxsize=1)
def get_storage_client() -> storage.Client:
    # Create lazily (not at import time) and pass project explicitly.
    return storage.Client(project=settings.gcp_project_id)


def upload_bytes(*, project_id: str, category: str, filename: str, content: bytes, content_type: str | None):
    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket_name)

    object_name = f"{project_id}/{category}/{filename}"
    blob = bucket.blob(object_name)
    blob.upload_from_string(content, content_type=content_type or "application/octet-stream")

    return {
        "bucket": settings.gcs_bucket_name,
        "object_name": object_name,
        "gcs_uri": f"gs://{settings.gcs_bucket_name}/{object_name}",
    }


def signed_get_url(object_name: str, expires_seconds: int = 3600) -> str | None:
    """Return signed URL when credentials support signing, otherwise None.

    In local/dev environments OAuth user credentials often cannot sign URLs.
    We intentionally return None instead of raising to avoid breaking upload APIs.
    """
    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(object_name)

    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_seconds),
            method="GET",
        )
    except (AttributeError, ValueError, TypeError):
        console.log("cannot sign url")
        return None


def download_bytes(object_name: str) -> bytes:
    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(object_name)
    return blob.download_as_bytes()
