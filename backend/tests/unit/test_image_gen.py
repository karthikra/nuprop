from __future__ import annotations

import pytest

from app.services.media import _fal, _s3, image_gen


@pytest.fixture
def _fake_fal(monkeypatch):
    """Return a fake fal.ai subscribe that yields a deterministic image payload."""
    captured: dict = {}

    async def _fake_subscribe(endpoint, arguments):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {
            "images": [
                {
                    "url": "https://fal.media/files/fake/output.png",
                    "width": 1024,
                    "height": 1024,
                    "content_type": "image/png",
                }
            ],
            "description": "an astronaut riding a horse",
        }

    monkeypatch.setattr(_fal, "fal_subscribe", _fake_subscribe)
    return captured


@pytest.fixture
def _fake_s3(monkeypatch):
    """Capture every S3 upload + presign GET; never hit the network."""
    uploads: list[dict] = []

    async def _fake_upload(*, key, body, content_type):
        uploads.append({"key": key, "body": body, "content_type": content_type})

    def _fake_presign_get(key):
        return f"https://s3.example/{key}?signed=yes"

    monkeypatch.setattr(_s3, "upload_bytes", _fake_upload)
    monkeypatch.setattr(_s3, "generate_presigned_get", _fake_presign_get)
    return uploads


@pytest.fixture
def _fake_download(monkeypatch):
    """Stub the httpx download of the fal-hosted image to return fixed bytes."""
    class _FakeResponse:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n FAKE PIXELS"

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr("app.services.media.image_gen.httpx.AsyncClient", _FakeClient)


async def test_generate_image_returns_asset_dict(
    _fake_fal, _fake_s3, _fake_download,
):
    asset = await image_gen.generate_image(
        prompt="an astronaut riding a horse",
        agency_id="agency-1",
        proposal_id="proposal-1",
    )

    assert asset["kind"] == "image"
    assert asset["ai_generated"] is True
    assert asset["provider"] == "fal-ai/nano-banana"
    assert asset["prompt"] == "an astronaut riding a horse"
    assert asset["width"] == 1024
    assert asset["height"] == 1024
    assert asset["caption"] is None
    assert asset["s3_key"].startswith("agency-1/proposal-1/")
    assert asset["s3_key"].endswith(".png")
    assert asset["url"] == f"https://s3.example/{asset['s3_key']}?signed=yes"
    assert "id" in asset


async def test_generate_image_uploads_to_s3_at_built_key(
    _fake_fal, _fake_s3, _fake_download,
):
    asset = await image_gen.generate_image(
        prompt="bird at dawn",
        agency_id="agency-1",
        proposal_id="proposal-1",
    )
    assert len(_fake_s3) == 1
    up = _fake_s3[0]
    assert up["key"] == asset["s3_key"]
    assert up["body"] == b"\x89PNG\r\n\x1a\n FAKE PIXELS"
    assert up["content_type"] == "image/png"


async def test_generate_image_calls_nano_banana_endpoint(
    _fake_fal, _fake_s3, _fake_download,
):
    await image_gen.generate_image(
        prompt="bird at dawn",
        agency_id="agency-1",
        proposal_id="proposal-1",
    )
    assert _fake_fal["endpoint"] == "fal-ai/nano-banana"
    assert _fake_fal["arguments"]["prompt"] == "bird at dawn"
    assert _fake_fal["arguments"]["num_images"] == 1
    assert _fake_fal["arguments"]["output_format"] == "png"


async def test_generate_image_raises_on_empty_fal_response(
    _fake_s3, _fake_download, monkeypatch,
):
    async def _fake_subscribe(endpoint, arguments):
        return {"images": []}

    monkeypatch.setattr(_fal, "fal_subscribe", _fake_subscribe)

    with pytest.raises(RuntimeError, match="returned no images"):
        await image_gen.generate_image(
            prompt="x",
            agency_id="agency-1",
            proposal_id="proposal-1",
        )
