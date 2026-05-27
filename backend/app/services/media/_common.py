"""Media common helpers — shared by every kind (image / video / audio).

Kept dependency-free (no boto3, no fal) so importing this module is cheap and
the unit tests don't need any network monkeypatching.

The ``Asset`` shape mirrors the spec's contract verbatim. Persisted into the
section JSON column's ``assets`` list. The ``url`` field is re-signed on every
read — never trust the persisted value past its 1h TTL.
"""
from __future__ import annotations

import enum
import uuid
from typing import TypedDict


class Kind(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


ALLOWED_MIMES: dict[str, set[str]] = {
    "image": {"image/jpeg", "image/png", "image/webp", "image/gif"},
    "video": {"video/mp4", "video/quicktime", "video/webm"},
    "audio": {"audio/mpeg", "audio/wav", "audio/mp4"},
}

MAX_BYTES: dict[str, int] = {
    "image": 10 * 1024 * 1024,    # 10 MB
    "video": 200 * 1024 * 1024,   # 200 MB
    "audio": 50 * 1024 * 1024,    # 50 MB
}

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/mp4": "m4a",
}


class Asset(TypedDict, total=False):
    id: str
    kind: str
    s3_key: str
    url: str | None              # presigned; re-signed on read; absent on write paths
    caption: str | None
    ai_generated: bool
    prompt: str | None
    provider: str | None
    width: int | None
    height: int | None
    duration_s: float | None
    poster_s3_key: str | None


def new_asset_id() -> str:
    """A fresh UUID4 string — collision-free for our scale."""
    return str(uuid.uuid4())


def ext_from_mime(content_type: str) -> str | None:
    """Look up the canonical extension for a known mime. ``None`` if unknown."""
    return _MIME_TO_EXT.get(content_type)


def build_s3_key(*, agency_id: str, proposal_id: str, asset_id: str, ext: str) -> str:
    """Canonical S3 object key: ``{agency_id}/{proposal_id}/{asset_id}.{ext}``."""
    return f"{agency_id}/{proposal_id}/{asset_id}.{ext}"


def validate_upload(*, kind: str, content_type: str, size: int) -> None:
    """Raise ``ValueError`` if the upload doesn't meet the kind's constraints."""
    if kind not in ALLOWED_MIMES:
        raise ValueError(f"Unknown asset kind: {kind!r}")
    if content_type not in ALLOWED_MIMES[kind]:
        raise ValueError(f"content_type {content_type!r} not allowed for {kind}")
    if size > MAX_BYTES[kind]:
        raise ValueError(
            f"size {size} bytes exceeds max size {MAX_BYTES[kind]} for {kind}"
        )
