from __future__ import annotations

import pytest

from app.services.media._common import (
    ALLOWED_MIMES,
    MAX_BYTES,
    Kind,
    build_s3_key,
    ext_from_mime,
    new_asset_id,
    validate_upload,
)


def test_kind_enum_has_three_values():
    assert {k.value for k in Kind} == {"image", "video", "audio"}


def test_ext_from_mime_known_types():
    assert ext_from_mime("image/jpeg") == "jpg"
    assert ext_from_mime("image/png") == "png"
    assert ext_from_mime("image/webp") == "webp"
    assert ext_from_mime("image/gif") == "gif"
    assert ext_from_mime("video/mp4") == "mp4"
    assert ext_from_mime("video/quicktime") == "mov"
    assert ext_from_mime("video/webm") == "webm"
    assert ext_from_mime("audio/mpeg") == "mp3"
    assert ext_from_mime("audio/wav") == "wav"
    assert ext_from_mime("audio/mp4") == "m4a"


def test_ext_from_mime_unknown_returns_none():
    assert ext_from_mime("application/pdf") is None
    assert ext_from_mime("") is None


def test_new_asset_id_is_a_uuid4_string():
    import uuid
    a = new_asset_id()
    b = new_asset_id()
    assert isinstance(a, str)
    parsed = uuid.UUID(a)            # raises ValueError if not a valid UUID
    assert parsed.version == 4       # specifically v4
    assert a != b


def test_build_s3_key_shape():
    key = build_s3_key(
        agency_id="agency-uuid",
        proposal_id="proposal-uuid",
        asset_id="asset-uuid",
        ext="png",
    )
    assert key == "agency-uuid/proposal-uuid/asset-uuid.png"


@pytest.mark.parametrize(
    "field,value",
    [
        ("agency_id", "../foo"),
        ("agency_id", "agency/with/slash"),
        ("proposal_id", "../"),
        ("asset_id", ".."),
        ("asset_id", "with space"),
    ],
)
def test_build_s3_key_rejects_unsafe_id_segments(field, value):
    args = {
        "agency_id": "agency-1",
        "proposal_id": "proposal-1",
        "asset_id": "asset-1",
        "ext": "png",
    }
    args[field] = value
    with pytest.raises(ValueError, match=field):
        build_s3_key(**args)


@pytest.mark.parametrize("bad_ext", ["png/..", "../etc", "PNG", "p" * 9, "", "p.g"])
def test_build_s3_key_rejects_unsafe_ext(bad_ext):
    with pytest.raises(ValueError, match="ext"):
        build_s3_key(
            agency_id="agency-1",
            proposal_id="proposal-1",
            asset_id="asset-1",
            ext=bad_ext,
        )


def test_validate_upload_accepts_in_range_image():
    validate_upload(kind="image", content_type="image/png", size=5 * 1024 * 1024)


@pytest.mark.parametrize(
    "kind,mime,size",
    [
        ("video", "video/mp4", 100 * 1024 * 1024),
        ("audio", "audio/mpeg", 10 * 1024 * 1024),
    ],
)
def test_validate_upload_accepts_in_range_video_and_audio(kind, mime, size):
    validate_upload(kind=kind, content_type=mime, size=size)


def test_validate_upload_rejects_oversize_image():
    with pytest.raises(ValueError, match="exceeds max size"):
        validate_upload(kind="image", content_type="image/png", size=11 * 1024 * 1024)


def test_validate_upload_rejects_disallowed_mime():
    with pytest.raises(ValueError, match="not allowed for image"):
        validate_upload(kind="image", content_type="application/pdf", size=1000)


def test_validate_upload_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown asset kind"):
        validate_upload(kind="poster", content_type="image/png", size=1000)


def test_allowed_mimes_image_set():
    assert ALLOWED_MIMES["image"] == {"image/jpeg", "image/png", "image/webp", "image/gif"}


def test_max_bytes_image_is_10mb():
    assert MAX_BYTES["image"] == 10 * 1024 * 1024
