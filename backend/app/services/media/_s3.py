"""boto3 wrapper — presigned URLs + raw uploads/deletes.

Sync boto3 is the right tool here:
- ``generate_presigned_url`` is pure local CPU (SigV4 signing) — calling it
  from an async handler is free; no offload needed.
- ``put_object`` / ``delete_object`` hit the network — wrap call-sites in
  ``asyncio.to_thread`` so the event loop isn't blocked.

The S3 client picks credentials from the AWS SDK credential chain (env vars,
profile, instance role) — same chain ``AsyncAnthropicBedrock`` uses. No extra
access-key setting in NUPROP config.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import get_settings

_PRESIGN_PUT_TTL = 15 * 60        # 15 minutes — the upload window
_PRESIGN_GET_TTL = 60 * 60        # 1 hour — the read TTL the spec promises


@lru_cache(maxsize=1)
def _s3_client():
    """Process-wide singleton. SigV4 explicit so older regions don't fall back to v2."""
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(signature_version="s3v4"),
    )


def generate_presigned_put(*, key: str, content_type: str, content_length: int) -> str:
    """Sign a single-use PUT URL the browser can use to upload directly to S3.

    ``content_type`` and ``content_length`` are baked into the signature; the
    browser MUST send the matching ``Content-Type`` and ``Content-Length`` headers
    or S3 will reject the PUT.
    """
    bucket = get_settings().NUPROP_S3_BUCKET
    return _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": content_length,
        },
        ExpiresIn=_PRESIGN_PUT_TTL,
    )


def generate_presigned_get(key: str) -> str:
    """Sign a 1h GET URL for an asset. Safe to call on every read."""
    bucket = get_settings().NUPROP_S3_BUCKET
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=_PRESIGN_GET_TTL,
    )


async def upload_bytes(*, key: str, body: bytes, content_type: str) -> None:
    """Async-safe PUT — blocks the threadpool, not the event loop."""
    bucket = get_settings().NUPROP_S3_BUCKET
    await asyncio.to_thread(
        _s3_client().put_object,
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )


async def delete_object(key: str) -> None:
    """Async-safe DELETE. Idempotent — S3 returns 204 even if key didn't exist."""
    bucket = get_settings().NUPROP_S3_BUCKET
    await asyncio.to_thread(_s3_client().delete_object, Bucket=bucket, Key=key)
