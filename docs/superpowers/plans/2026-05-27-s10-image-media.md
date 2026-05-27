# S10 — Image Media (Upload + AI Generation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every proposal section carry **image** assets — uploaded directly to S3 by the user (presigned PUT, bypasses Python) or generated on demand via fal.ai Nano Banana. Asset metadata lives inside the section's existing JSON column (`assets[]`). Video and audio land in S11; the same endpoints widen by `kind` then.

**Architecture:** New `nuprop-proposal-assets` S3 bucket (private, `ap-northeast-1`, 90-day lifecycle on un-tagged objects). Backend gains a thin `services/media/` package — a sync boto3 wrapper, an async fal.ai wrapper, common helpers (key shape, mime/size validation, presign), and an `image_gen.py` that calls Nano Banana, downloads the result, uploads to S3, and returns an `Asset` dict. Four section-scoped endpoints (`/assets/presign`, `/commit`, `/generate`, `/delete`) mutate the `Proposal.<section_type>["assets"]` list. Reads re-sign URLs on every GET (1h TTL); writes return the freshly signed asset. Frontend adds an asset thumbnail row + an "Add image" split-button (Upload | Generate with AI) under each section block.

**Tech Stack:** Python 3.13 / boto3 (sync, called via `asyncio.to_thread` for network) / `fal-client>=0.5.0` (`subscribe_async`) / httpx (download from fal CDN) / FastAPI / SQLAlchemy async / React 18 / TypeScript / React Query v5 / vitest + MSW.

**Spec:** `docs/superpowers/specs/2026-05-26-s9-s13-section-redesign-design.md` (Piece D — Media model; Piece A — `Asset` shape; S10 slice block).

**Working directory:** backend paths relative to `backend/`; frontend paths relative to `frontend/`. Both stacks are touched.

**Out of scope (deferred to S11/S12):** video + audio kinds, first-frame poster extraction, share-token / Publish flow, asset tagging on publish, NUSTAGE handoff. The `/generate` endpoint accepts `kind` in the body but S10 rejects anything except `"image"` so S11 can widen without a contract change.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/pyproject.toml` | Add `fal-client>=0.5.0` to `dependencies` | Modify |
| `backend/app/core/config.py` | Add `FAL_KEY` and `NUPROP_S3_BUCKET` settings | Modify |
| `backend/app/services/media/__init__.py` | Package marker | Create |
| `backend/app/services/media/_common.py` | Asset constants (kinds, mime/ext maps, size caps), key builder, validation helpers, `Asset` TypedDict | Create |
| `backend/app/services/media/_s3.py` | Cached boto3 client; `generate_presigned_put`, `generate_presigned_get`, `upload_bytes`, `delete_object` | Create |
| `backend/app/services/media/_fal.py` | Thin async wrapper around `fal_client.subscribe_async` — single seam tests monkeypatch | Create |
| `backend/app/services/media/image_gen.py` | `async def generate_image(prompt, agency_id, proposal_id) -> dict` — Nano Banana → download → S3 upload → `Asset` | Create |
| `backend/app/services/media/section_assets.py` | Pure helpers: `append_asset_to_section`, `remove_asset_from_section`, `resign_assets`, `default_section_for_assets` | Create |
| `backend/app/views/v1/proposals.py` | Four new asset endpoints under `/proposals/{id}/sections/{type}/assets/...`; re-sign helper applied to section returns | Modify |
| `backend/app/viewmodels/proposal_viewmodel.py` | Resign section assets when returning a single proposal (GET endpoint path) | Modify |
| `backend/tests/conftest.py` | Extend `_no_network` to also block real fal + S3 network calls | Modify |
| `backend/tests/unit/test_media_common.py` | Unit tests for `_common.py` (key shape, mime/size validation, ext lookup) | Create |
| `backend/tests/unit/test_image_gen.py` | Unit tests for `image_gen.py` with fal + S3 monkeypatched | Create |
| `backend/tests/integration/test_asset_endpoints.py` | Integration tests for the four endpoints + cross-agency IDOR + re-sign-on-GET | Create |
| `backend/scripts/bootstrap_s3.sh` | Idempotent AWS CLI script — create bucket, block public access, CORS, lifecycle | Create |
| `frontend/src/api/proposals.ts` | Hooks: `usePresignAsset`, `useCommitAsset`, `useGenerateAsset`, `useDeleteAsset` | Modify |
| `frontend/src/components/sections/asset-row.tsx` | Renders `section.assets[]` as thumbnails with caption + delete | Create |
| `frontend/src/components/sections/add-image-menu.tsx` | Split-button: "Upload file" (file picker → presign → PUT → commit) and "Generate with AI" (prompt dialog → /generate) | Create |
| `frontend/src/components/sections/section-block.tsx` | Mount AssetRow + AddImageMenu under the textarea | Modify |
| `frontend/src/components/sections/__tests__/asset-row.test.tsx` | Render thumbnails, trigger delete | Create |
| `frontend/src/components/sections/__tests__/add-image-menu.test.tsx` | Upload flow (presign + PUT + commit); generate flow (prompt → /generate) | Create |
| `docs/superpowers/HANDOFF.md` | Mark S10 complete; new "What happened this session" block | Modify |

---

### Task 1: Add `fal-client` dep + media settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add `fal-client` to `dependencies` in `backend/pyproject.toml`**

In the `dependencies = [ ... ]` list of `backend/pyproject.toml`, add `fal-client>=0.5.0` (alphabetic order, immediately after `email-validator`):

```toml
    "email-validator>=2.3.0",
    "fal-client>=0.5.0",
    "bcrypt>=5.0.0",
```

(`bcrypt` and `weasyprint` should keep their existing positions; `fal-client` slots in alphabetically.)

- [ ] **Step 2: Sync the lock**

Run: `cd backend && uv sync`
Expected: lockfile updates; `fal-client` and its transitive deps (`httpx-sse`, `tenacity`) are added. No diff on other packages.

- [ ] **Step 3: Modify `backend/app/core/config.py` to add the media-related settings**

In the `Settings` class, just under the existing `# Web search` block, add:

```python
    # Media — fal.ai for AI generation, S3 for asset storage.
    FAL_KEY: str = ""
    NUPROP_S3_BUCKET: str = "nuprop-proposal-assets"
```

The S3 client reads `AWS_REGION` (already declared) and uses the SDK credential chain — no extra access-key setting needed.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py
git commit -m "feat(S10): add fal-client dep and FAL_KEY/NUPROP_S3_BUCKET settings"
```

---

### Task 2: Media common helpers — `Asset` shape, kinds, validation, key builder

**Files:**
- Create: `backend/app/services/media/__init__.py`
- Create: `backend/app/services/media/_common.py`
- Create: `backend/tests/unit/test_media_common.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_media_common.py`:

```python
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
    a = new_asset_id()
    b = new_asset_id()
    assert isinstance(a, str)
    assert len(a) == 36
    assert a != b  # 1-in-2**122 collision; safe


def test_build_s3_key_shape():
    key = build_s3_key(
        agency_id="agency-uuid",
        proposal_id="proposal-uuid",
        asset_id="asset-uuid",
        ext="png",
    )
    assert key == "agency-uuid/proposal-uuid/asset-uuid.png"


def test_validate_upload_accepts_in_range_image():
    validate_upload(kind="image", content_type="image/png", size=5 * 1024 * 1024)


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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_media_common.py -v 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: app.services.media`.

- [ ] **Step 3: Create the package marker**

Create `backend/app/services/media/__init__.py` (empty):

```python
```

- [ ] **Step 4: Implement `_common.py`**

Create `backend/app/services/media/_common.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_media_common.py -v 2>&1 | tail -20`
Expected: PASS — 10 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/media/__init__.py backend/app/services/media/_common.py backend/tests/unit/test_media_common.py
git commit -m "feat(S10): media common helpers — Asset shape, kinds, validation, key builder"
```

---

### Task 3: S3 wrapper — cached boto3 client + presign + upload + delete

**Files:**
- Create: `backend/app/services/media/_s3.py`

This task ships the wrapper but doesn't add a unit test for it — boto3's `generate_presigned_url` is pure local CPU and round-tripped through the integration tests in Task 8. There's nothing meaningful to assert in isolation without hitting AWS.

- [ ] **Step 1: Implement `_s3.py`**

Create `backend/app/services/media/_s3.py`:

```python
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
```

- [ ] **Step 2: Confirm the module imports cleanly**

Run: `.venv/bin/python -c "from app.services.media import _s3; print(_s3.generate_presigned_put.__doc__.splitlines()[0])"`
Expected: a single line `Sign a single-use PUT URL the browser can use to upload directly to S3.`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/media/_s3.py
git commit -m "feat(S10): boto3 wrapper — presigned PUT/GET, async-safe upload/delete"
```

---

### Task 4: fal.ai async wrapper — single seam for monkeypatching

**Files:**
- Create: `backend/app/services/media/_fal.py`

- [ ] **Step 1: Implement `_fal.py`**

Create `backend/app/services/media/_fal.py`:

```python
"""fal.ai async wrapper.

Why a wrapper:
- ``fal_client.subscribe_async`` reads ``FAL_KEY`` from ``os.environ`` at call
  time. Setting it via NUPROP's pydantic-settings doesn't help unless we
  forward it; we do that here.
- Tests monkeypatch this one function (``app.services.media._fal.fal_subscribe``)
  to avoid the optional ``fal-client`` import in test environments where it's
  not installed and to block real network calls.
"""
from __future__ import annotations

import os
from typing import Any

from app.core.config import get_settings


async def fal_subscribe(endpoint: str, arguments: dict[str, Any]) -> dict:
    """Submit a job to fal.ai and await the result.

    Imported lazily so the test suite can monkeypatch ``fal_subscribe`` before
    ``fal_client`` is imported (and never trigger the real network).
    """
    settings = get_settings()
    if settings.FAL_KEY and not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = settings.FAL_KEY

    import fal_client  # local import — see docstring

    return await fal_client.subscribe_async(
        endpoint,
        arguments=arguments,
        with_logs=False,
    )
```

- [ ] **Step 2: Confirm import**

Run: `.venv/bin/python -c "from app.services.media._fal import fal_subscribe; print(fal_subscribe.__name__)"`
Expected: `fal_subscribe`. The `fal_client` import is lazy so this works even before `uv sync`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/media/_fal.py
git commit -m "feat(S10): async fal.ai wrapper — single seam for test monkeypatching"
```

---

### Task 5: Image-gen service — Nano Banana → S3 → Asset

**Files:**
- Create: `backend/app/services/media/image_gen.py`
- Create: `backend/tests/unit/test_image_gen.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_image_gen.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_image_gen.py -v 2>&1 | tail -20`
Expected: FAIL — `ImportError: cannot import name 'image_gen' from 'app.services.media'`.

- [ ] **Step 3: Implement `image_gen.py`**

Create `backend/app/services/media/image_gen.py`:

```python
"""Image generation via fal.ai Nano Banana → S3 → ``Asset`` dict.

Flow: subscribe to Nano Banana → download the returned image from fal's CDN →
upload to NUPROP's S3 bucket → return an ``Asset`` dict with a freshly signed
GET URL. The asset's ``s3_key`` is canonical; ``url`` is convenience that
callers re-sign whenever they read.
"""
from __future__ import annotations

import httpx

from app.services.media import _fal, _s3
from app.services.media._common import (
    Asset,
    build_s3_key,
    ext_from_mime,
    new_asset_id,
)

_ENDPOINT = "fal-ai/nano-banana"
_PROVIDER = _ENDPOINT
_DEFAULT_CONTENT_TYPE = "image/png"
_DOWNLOAD_TIMEOUT_S = 60.0


async def generate_image(
    *,
    prompt: str,
    agency_id: str,
    proposal_id: str,
) -> Asset:
    """Submit ``prompt`` to Nano Banana; persist the result in S3; return ``Asset``.

    Raises ``RuntimeError`` if fal.ai returns no images (rare — usually a content
    policy violation; surfaced as a 502 by the caller).
    """
    response = await _fal.fal_subscribe(
        _ENDPOINT,
        arguments={
            "prompt": prompt,
            "num_images": 1,
            "output_format": "png",
        },
    )

    images = response.get("images") or []
    if not images:
        raise RuntimeError(f"fal.ai endpoint {_ENDPOINT} returned no images")

    first = images[0]
    fal_url = first["url"]
    content_type = first.get("content_type") or _DEFAULT_CONTENT_TYPE
    width = first.get("width")
    height = first.get("height")

    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT_S) as http:
        download = await http.get(fal_url)
        download.raise_for_status()
        body = download.content

    asset_id = new_asset_id()
    ext = ext_from_mime(content_type) or "png"
    s3_key = build_s3_key(
        agency_id=str(agency_id),
        proposal_id=str(proposal_id),
        asset_id=asset_id,
        ext=ext,
    )
    await _s3.upload_bytes(key=s3_key, body=body, content_type=content_type)

    return Asset(
        id=asset_id,
        kind="image",
        s3_key=s3_key,
        url=_s3.generate_presigned_get(s3_key),
        caption=None,
        ai_generated=True,
        prompt=prompt,
        provider=_PROVIDER,
        width=width,
        height=height,
        duration_s=None,
        poster_s3_key=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_image_gen.py -v 2>&1 | tail -20`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/media/image_gen.py backend/tests/unit/test_image_gen.py
git commit -m "feat(S10): image_gen service — Nano Banana → S3 → Asset"
```

---

### Task 6: Section-asset helpers — append, remove, resign URLs

**Files:**
- Create: `backend/app/services/media/section_assets.py`
- Create: `backend/tests/unit/test_section_assets.py`

These are pure-Python helpers over the section dict. Keeping them out of the route handlers means the integration tests don't have to re-verify their behavior.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_section_assets.py`:

```python
from __future__ import annotations

from app.services.media.section_assets import (
    append_asset_to_section,
    default_section_for_assets,
    remove_asset_from_section,
    resign_assets,
)


def test_default_section_for_assets_neutral_payload():
    s = default_section_for_assets()
    assert s == {"content": "", "assets": [], "included": True, "metadata": {}}


def test_append_asset_to_none_section_initialises_default():
    new = append_asset_to_section(None, {"id": "a1", "kind": "image", "s3_key": "k1"})
    assert new["content"] == ""
    assert new["included"] is True
    assert new["assets"] == [{"id": "a1", "kind": "image", "s3_key": "k1"}]


def test_append_asset_preserves_existing_content_and_assets():
    current = {
        "content": "hello",
        "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
        "included": True,
        "metadata": {"k": "v"},
    }
    new = append_asset_to_section(current, {"id": "a2", "kind": "image", "s3_key": "k2"})
    assert new["content"] == "hello"
    assert new["metadata"] == {"k": "v"}
    assert len(new["assets"]) == 2
    assert new["assets"][1]["id"] == "a2"


def test_remove_asset_returns_section_minus_matching_asset():
    current = {
        "content": "hi",
        "assets": [
            {"id": "a1", "kind": "image", "s3_key": "k1"},
            {"id": "a2", "kind": "image", "s3_key": "k2"},
        ],
        "included": True,
        "metadata": {},
    }
    new, removed = remove_asset_from_section(current, asset_id="a1")
    assert removed == {"id": "a1", "kind": "image", "s3_key": "k1"}
    assert [a["id"] for a in new["assets"]] == ["a2"]


def test_remove_asset_returns_none_when_not_found():
    current = {
        "content": "",
        "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
        "included": True,
        "metadata": {},
    }
    new, removed = remove_asset_from_section(current, asset_id="missing")
    assert removed is None
    assert new == current


def test_resign_assets_replaces_url_using_provided_signer():
    section = {
        "content": "",
        "assets": [
            {"id": "a1", "kind": "image", "s3_key": "k1", "url": "stale"},
            {"id": "a2", "kind": "image", "s3_key": "k2"},
        ],
        "included": True,
        "metadata": {},
    }
    resigned = resign_assets(section, signer=lambda key: f"signed://{key}")
    assert resigned["assets"][0]["url"] == "signed://k1"
    assert resigned["assets"][1]["url"] == "signed://k2"
    # Original list/dicts not mutated
    assert section["assets"][0]["url"] == "stale"


def test_resign_assets_on_none_or_empty_returns_input_unchanged():
    assert resign_assets(None, signer=lambda _: "x") is None
    assert resign_assets({"assets": []}, signer=lambda _: "x") == {"assets": []}
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_section_assets.py -v 2>&1 | tail -20`
Expected: FAIL — `ImportError: cannot import name 'section_assets'`.

- [ ] **Step 3: Implement `section_assets.py`**

Create `backend/app/services/media/section_assets.py`:

```python
"""Pure helpers over the section dict — never call S3 or fal directly.

Section shape (lives on the JSON column):
    {"content": str, "assets": list[Asset], "included": bool, "metadata": dict}

Asset URLs aren't trusted past their TTL — readers always re-sign through
``resign_assets`` before serving a proposal.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy


def default_section_for_assets() -> dict:
    """Neutral section payload used when appending an asset to a NULL column."""
    return {"content": "", "assets": [], "included": True, "metadata": {}}


def append_asset_to_section(section: dict | None, asset: dict) -> dict:
    """Return a new section dict with ``asset`` appended to ``assets``."""
    base = deepcopy(section) if section else default_section_for_assets()
    base.setdefault("assets", [])
    base["assets"] = [*base["assets"], asset]
    return base


def remove_asset_from_section(section: dict, *, asset_id: str) -> tuple[dict, dict | None]:
    """Return ``(new_section, removed_asset_or_None)``."""
    assets = section.get("assets") or []
    removed = next((a for a in assets if a.get("id") == asset_id), None)
    if removed is None:
        return section, None
    new = deepcopy(section)
    new["assets"] = [a for a in assets if a.get("id") != asset_id]
    return new, removed


def resign_assets(
    section: dict | None,
    *,
    signer: Callable[[str], str],
) -> dict | None:
    """Return a new section with every asset's ``url`` re-signed.

    ``signer(s3_key) -> presigned_url``. No-op for sections with no assets;
    returns ``None`` if the section itself is ``None``.
    """
    if section is None:
        return None
    assets = section.get("assets") or []
    if not assets:
        return section
    new = deepcopy(section)
    new["assets"] = [
        {**a, "url": signer(a["s3_key"])} for a in assets
    ]
    return new


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_section_assets.py -v 2>&1 | tail -20`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/media/section_assets.py backend/tests/unit/test_section_assets.py
git commit -m "feat(S10): pure section-asset helpers — append/remove/resign"
```

---

### Task 7: Extend the test-suite no-network guard to fal + S3

**Files:**
- Modify: `backend/tests/conftest.py`

Today's `_no_network` only blocks `AnthropicClient`. Add belt-and-braces patches so an accidentally-unstubbed call in any future test fails loudly instead of silently hitting AWS / fal.

- [ ] **Step 1: Modify `_no_network` to also block fal + S3 network methods**

Locate the `_no_network` fixture in `backend/tests/conftest.py` (the one that already monkeypatches `AnthropicClient`). Below the last `monkeypatch.setattr(AnthropicClient, ...)` line, add:

```python
    # Media — fal.ai + S3 network calls must never run for real in tests.
    async def _blocked_async_media(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Real fal.ai call attempted during a test")

    async def _blocked_async_upload(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Real S3 upload_bytes attempted during a test")

    async def _blocked_async_delete(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Real S3 delete_object attempted during a test")

    def _fake_presign_get(key: str) -> str:
        return f"https://s3.example/{key}?signed=test"

    def _fake_presign_put(*, key, content_type, content_length):  # noqa: ANN001
        return f"https://s3.example/{key}?upload=test"

    monkeypatch.setattr(
        "app.services.media._fal.fal_subscribe", _blocked_async_media, raising=False,
    )
    monkeypatch.setattr(
        "app.services.media._s3.upload_bytes", _blocked_async_upload, raising=False,
    )
    monkeypatch.setattr(
        "app.services.media._s3.delete_object", _blocked_async_delete, raising=False,
    )
    monkeypatch.setattr(
        "app.services.media._s3.generate_presigned_get", _fake_presign_get, raising=False,
    )
    monkeypatch.setattr(
        "app.services.media._s3.generate_presigned_put", _fake_presign_put, raising=False,
    )
```

The presign helpers are stubbed to deterministic URLs so any test asserting on the returned URL gets a predictable string. Tests that need a different fal/S3 behavior layer per-test patches on top — `monkeypatch.setattr` calls inside a test always win over the autouse fixture.

- [ ] **Step 2: Confirm suite still passes**

Run: `.venv/bin/python -m pytest -q 2>&1 | tail -10`
Expected: PASS — same count as before this task (~406 + the new media-common + image-gen + section-assets tests landed so far ≈ ~421).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(S10): block real fal/S3 network calls in the no-network fixture"
```

---

### Task 8: Asset endpoints — presign / commit / generate / delete

**Files:**
- Modify: `backend/app/views/v1/proposals.py`
- Create: `backend/tests/integration/test_asset_endpoints.py`

These four endpoints sit alongside the existing section CRUD routes. They mutate the same `Proposal.<section_type>` JSON column via the section-asset helpers from Task 6.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_asset_endpoints.py`:

```python
"""Integration tests for section-asset endpoints.

POST   /api/v1/proposals/{id}/sections/{type}/assets/presign
POST   /api/v1/proposals/{id}/sections/{type}/assets/commit
POST   /api/v1/proposals/{id}/sections/{type}/assets/generate
DELETE /api/v1/proposals/{id}/sections/{type}/assets/{asset_id}
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


async def _setup(http, headers):
    c = (await http.post(f"{API}/clients", headers=headers, json={"name": "Assets Client"})).json()
    p = (await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Assets Project"},
    )).json()
    return p


@pytest_asyncio.fixture
async def _proposal(client, registered, db):
    p = await _setup(client, registered.headers)
    # Stamp a section so /commit and /delete have somewhere to read from.
    await ProposalRepository(db).update(
        p["id"],
        problem_statement={"content": "x", "assets": [], "included": True, "metadata": {}},
    )
    await db.commit()
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    return proposal, registered.headers


# ── presign ──────────────────────────────────────────────────────────────────
async def test_presign_returns_upload_url_and_asset_id(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "hero.png", "content_type": "image/png", "size": 1024},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upload_url"].startswith("https://s3.example/")
    assert body["s3_key"].endswith(".png")
    assert body["s3_key"].startswith(f"{proposal.agency_id}/{proposal.id}/")
    assert "asset_id" in body


async def test_presign_rejects_oversize_image(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "huge.png", "content_type": "image/png", "size": 11 * 1024 * 1024},
    )
    assert r.status_code == 400
    assert "exceeds max size" in r.json()["detail"]


async def test_presign_rejects_wrong_mime(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "doc.pdf", "content_type": "application/pdf", "size": 1024},
    )
    assert r.status_code == 400
    assert "not allowed for image" in r.json()["detail"]


async def test_presign_unknown_section_type_returns_400(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/not_a_section/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "x.png", "content_type": "image/png", "size": 100},
    )
    assert r.status_code == 400


# ── commit ───────────────────────────────────────────────────────────────────
async def test_commit_appends_asset_to_section(client, _proposal, db):
    proposal, headers = _proposal
    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    presigned = r1.json()

    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": presigned["asset_id"],
            "s3_key": presigned["s3_key"],
            "kind": "image",
            "content_type": "image/png",
            "caption": "hero shot",
            "width": 1024,
            "height": 768,
        },
    )
    assert r2.status_code == 200, r2.text
    asset = r2.json()
    assert asset["id"] == presigned["asset_id"]
    assert asset["s3_key"] == presigned["s3_key"]
    assert asset["caption"] == "hero shot"
    assert asset["ai_generated"] is False
    assert asset["provider"] == "upload"
    assert asset["url"].startswith("https://s3.example/")

    # Verify it was persisted on the section's assets list.
    refreshed = await ProposalRepository(db).get_by_id(proposal.id)
    assert refreshed.problem_statement["assets"][0]["id"] == presigned["asset_id"]


async def test_commit_persists_when_section_column_is_null(client, _proposal, db):
    """Committing to a section that's still NULL initialises a default payload."""
    proposal, headers = _proposal
    # Wipe the section back to NULL.
    await ProposalRepository(db).update(proposal.id, problem_statement=None)
    await db.commit()

    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    p = r1.json()
    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": p["asset_id"],
            "s3_key": p["s3_key"],
            "kind": "image",
            "content_type": "image/png",
            "caption": None,
            "width": None,
            "height": None,
        },
    )
    assert r2.status_code == 200

    refreshed = await ProposalRepository(db).get_by_id(proposal.id)
    section = refreshed.problem_statement
    assert section["content"] == ""
    assert section["included"] is True
    assert len(section["assets"]) == 1


# ── generate ─────────────────────────────────────────────────────────────────
async def test_generate_image_appends_ai_asset(client, _proposal, db, monkeypatch):
    proposal, headers = _proposal

    async def _fake_generate_image(*, prompt, agency_id, proposal_id):
        return {
            "id": "ai-asset-1",
            "kind": "image",
            "s3_key": f"{agency_id}/{proposal_id}/ai-asset-1.png",
            "url": "https://s3.example/will-be-overwritten?signed=fake",
            "caption": None,
            "ai_generated": True,
            "prompt": prompt,
            "provider": "fal-ai/nano-banana",
            "width": 1024,
            "height": 1024,
            "duration_s": None,
            "poster_s3_key": None,
        }

    import app.views.v1.proposals as proposals_view
    monkeypatch.setattr(proposals_view, "generate_image", _fake_generate_image, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "image", "prompt": "an astronaut"},
    )
    assert r.status_code == 200, r.text
    asset = r.json()
    assert asset["ai_generated"] is True
    assert asset["prompt"] == "an astronaut"
    # The handler re-signs via the test stub of generate_presigned_get.
    assert asset["url"] == f"https://s3.example/{asset['s3_key']}?signed=test"

    refreshed = await ProposalRepository(db).get_by_id(proposal.id)
    assert refreshed.problem_statement["assets"][0]["id"] == "ai-asset-1"


async def test_generate_rejects_non_image_kind_in_s10(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "video", "prompt": "x"},
    )
    assert r.status_code == 400
    assert "image" in r.json()["detail"]


# ── delete ───────────────────────────────────────────────────────────────────
async def test_delete_removes_asset_from_section(client, _proposal, db, monkeypatch):
    proposal, headers = _proposal
    # Seed an asset directly.
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "x",
            "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    deleted: list[str] = []

    async def _fake_delete(key):
        deleted.append(key)

    monkeypatch.setattr("app.services.media._s3.delete_object", _fake_delete, raising=False)

    r = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/a1",
        headers=headers,
    )
    assert r.status_code == 204
    assert deleted == ["k1"]

    refreshed = await ProposalRepository(db).get_by_id(proposal.id)
    assert refreshed.problem_statement["assets"] == []


async def test_delete_missing_asset_returns_404(client, _proposal):
    proposal, headers = _proposal
    r = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/missing",
        headers=headers,
    )
    assert r.status_code == 404


# ── IDOR isolation ───────────────────────────────────────────────────────────
async def test_asset_endpoints_404_for_other_agency(client, _proposal, second_agency):
    proposal, _ = _proposal
    rival = second_agency.headers

    presign = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=rival,
        json={"kind": "image", "filename": "x.png", "content_type": "image/png", "size": 100},
    )
    assert presign.status_code == 404

    commit = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=rival,
        json={
            "asset_id": "x", "s3_key": "k", "kind": "image",
            "content_type": "image/png", "caption": None, "width": None, "height": None,
        },
    )
    assert commit.status_code == 404

    gen = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=rival,
        json={"kind": "image", "prompt": "x"},
    )
    assert gen.status_code == 404

    delete = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/x",
        headers=rival,
    )
    assert delete.status_code == 404
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_asset_endpoints.py -v 2>&1 | tail -30`
Expected: FAIL — the endpoints don't exist; 404 on every POST/DELETE.

- [ ] **Step 3: Implement the four endpoints in `backend/app/views/v1/proposals.py`**

Add the following imports at the top of the file (alongside the existing imports):

```python
from app.services.media import _s3
from app.services.media._common import (
    Asset,
    build_s3_key,
    ext_from_mime,
    new_asset_id,
    validate_upload,
)
from app.services.media.image_gen import generate_image
from app.services.media.section_assets import (
    append_asset_to_section,
    default_section_for_assets,
    remove_asset_from_section,
)
```

Add the Pydantic bodies near the existing `PatchSectionBody` definition:

```python
class PresignAssetBody(BaseModel):
    kind: str
    filename: str
    content_type: str
    size: int


class CommitAssetBody(BaseModel):
    asset_id: str
    s3_key: str
    kind: str
    content_type: str
    caption: str | None = None
    width: int | None = None
    height: int | None = None


class GenerateAssetBody(BaseModel):
    kind: str
    prompt: str
```

Add a helper that resolves and authorizes the proposal (mirrors the existing pattern in the section CRUD endpoints):

```python
async def _resolve_proposal(repo: ProposalRepository, proposal_id: UUID, agency_id: UUID):
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def _resign_asset(asset: dict) -> dict:
    """Re-sign a single asset's ``url`` from its ``s3_key`` (returns a copy)."""
    return {**asset, "url": _s3.generate_presigned_get(asset["s3_key"])}
```

Now append the four endpoints **after** the existing `/refine` endpoint:

```python
# ── Section asset endpoints (S10: image only; S11 widens kind) ───────────────


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/presign",
    status_code=200,
)
async def presign_asset(
    proposal_id: UUID,
    section_type: str,
    body: PresignAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    try:
        validate_upload(kind=body.kind, content_type=body.content_type, size=body.size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ext = ext_from_mime(body.content_type) or "bin"
    asset_id = new_asset_id()
    s3_key = build_s3_key(
        agency_id=str(proposal.agency_id),
        proposal_id=str(proposal.id),
        asset_id=asset_id,
        ext=ext,
    )
    upload_url = _s3.generate_presigned_put(
        key=s3_key,
        content_type=body.content_type,
        content_length=body.size,
    )
    return {"upload_url": upload_url, "s3_key": s3_key, "asset_id": asset_id}


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/commit",
    status_code=200,
)
async def commit_asset(
    proposal_id: UUID,
    section_type: str,
    body: CommitAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    if body.kind not in ("image", "video", "audio"):
        raise HTTPException(status_code=400, detail=f"Unknown kind: {body.kind}")

    asset: dict = {
        "id": body.asset_id,
        "kind": body.kind,
        "s3_key": body.s3_key,
        "caption": body.caption,
        "ai_generated": False,
        "prompt": None,
        "provider": "upload",
        "width": body.width,
        "height": body.height,
        "duration_s": None,
        "poster_s3_key": None,
    }
    current = getattr(proposal, section_type)
    new_section = append_asset_to_section(current, asset)
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    return _resign_asset(asset)


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/generate",
    status_code=200,
)
async def generate_asset(
    proposal_id: UUID,
    section_type: str,
    body: GenerateAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    if body.kind != "image":
        raise HTTPException(
            status_code=400,
            detail=f"Generation for kind={body.kind!r} is not supported yet (S10 ships image only)",
        )

    asset = await generate_image(
        prompt=body.prompt,
        agency_id=str(proposal.agency_id),
        proposal_id=str(proposal.id),
    )
    current = getattr(proposal, section_type)
    new_section = append_asset_to_section(current, asset)
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    return _resign_asset(asset)


@router.delete(
    "/{proposal_id}/sections/{section_type}/assets/{asset_id}",
    status_code=204,
)
async def delete_asset(
    proposal_id: UUID,
    section_type: str,
    asset_id: str,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    current = getattr(proposal, section_type)
    if not current or not current.get("assets"):
        raise HTTPException(status_code=404, detail="Asset not found")

    new_section, removed = remove_asset_from_section(current, asset_id=asset_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    await _s3.delete_object(removed["s3_key"])
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run the integration tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/test_asset_endpoints.py -v 2>&1 | tail -40`
Expected: PASS — 12 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/views/v1/proposals.py backend/tests/integration/test_asset_endpoints.py
git commit -m "feat(S10): per-section asset endpoints — presign/commit/generate/delete + IDOR"
```

---

### Task 9: Re-sign asset URLs on every proposal-shaped response

**Files:**
- Modify: `backend/app/views/v1/proposals.py`
- Modify: `backend/tests/integration/test_asset_endpoints.py`

Persisted asset URLs go stale after 1h. Every endpoint that returns `ProposalResponse` (GET, PATCH proposal, etc.) must re-sign every asset on read so the frontend never serves a 403 to the user. The PATCH/regenerate/refine returns from S9 only ever produce empty `assets[]` so they don't need this; the per-asset write endpoints from Task 8 already call `_resign_asset` on the freshly-written asset.

**Important:** `app/infrastructure/db/database.py:42` commits the session on the way out of `get_db`. That means mutating `proposal.<section_type>` on the **SA model** would persist the re-signed (transient) URL to the DB. The re-sign must happen on the **serialized response object**, not the model.

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/integration/test_asset_endpoints.py` (at the bottom of the file):

```python
async def test_get_proposal_resigns_every_asset_url(client, _proposal, db):
    proposal, headers = _proposal
    # Seed two assets directly, both with stale URLs.
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "x",
            "assets": [
                {"id": "a1", "kind": "image", "s3_key": "k1", "url": "stale-1"},
                {"id": "a2", "kind": "image", "s3_key": "k2", "url": "stale-2"},
            ],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    r = await client.get(f"{API}/proposals/{proposal.id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assets = body["problem_statement"]["assets"]
    assert assets[0]["url"] == "https://s3.example/k1?signed=test"
    assert assets[1]["url"] == "https://s3.example/k2?signed=test"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_asset_endpoints.py::test_get_proposal_resigns_every_asset_url -v 2>&1 | tail -15`
Expected: FAIL — URLs return as `"stale-1"` / `"stale-2"` because no re-sign hook is wired in yet.

- [ ] **Step 3: Add a re-sign helper that operates on `ProposalResponse`, and use it in the route handlers**

Open `backend/app/views/v1/proposals.py`. The imports added in Task 8 already include `_s3`. Add the section-assets import line at the top of the file (alongside the other Task-8 imports):

```python
from app.services.media.section_assets import resign_assets
from app.services.sections import SECTION_ORDER
```

Add the helper just above the `router = APIRouter(...)` line:

```python
def _resign_response_sections(resp: ProposalResponse) -> ProposalResponse:
    """Return ``resp`` with every section's ``assets[].url`` freshly signed.

    Operates on the Pydantic response — never mutates the SA model (that would
    be persisted by ``get_db``'s on-exit commit).
    """
    for col in SECTION_ORDER:
        current = getattr(resp, col, None)
        if current is None or not current.get("assets"):
            continue
        setattr(resp, col, resign_assets(current, signer=_s3.generate_presigned_get))
    return resp
```

Modify the existing `GET /proposals/{proposal_id}` handler (around line 72) to re-sign before returning:

```python
@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.get_proposal(proposal_id, agency_id)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return _resign_response_sections(ProposalResponse.model_validate(proposal))
```

Modify the existing `PATCH /proposals/{proposal_id}` handler similarly — `vm.update_proposal(...)` returns an SA `Proposal`; serialize then re-sign:

```python
@router.patch("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: UUID,
    data: ProposalUpdate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.update_proposal(proposal_id, agency_id, data)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return _resign_response_sections(ProposalResponse.model_validate(proposal))
```

The `POST /proposals` (create), preferences PATCH, and DELETE endpoints either return a brand-new (asset-less) proposal or a 204 — no re-sign needed.

- [ ] **Step 4: Run the new test plus the suite to verify**

Run: `.venv/bin/python -m pytest tests/integration/test_asset_endpoints.py -v 2>&1 | tail -20`
Expected: PASS — 13 tests (12 from Task 8 + this one).

Run: `.venv/bin/python -m pytest -q 2>&1 | tail -10`
Expected: PASS — no other test regressed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/views/v1/proposals.py backend/tests/integration/test_asset_endpoints.py
git commit -m "feat(S10): re-sign every asset URL on proposal-shaped responses"
```

---

### Task 10: S3 bucket bootstrap script (one-time operator step)

**Files:**
- Create: `backend/scripts/bootstrap_s3.sh`

This is the spec's "Create S3 bucket via Terraform/CloudFormation (or Fly secrets pointing at an existing bucket; decided in S10 spec)" — the decision is **idempotent shell script** to match the hand-managed-infra style of this repo (no Terraform/CFN anywhere else; the only IaC-equivalent is `fly.toml`).

- [ ] **Step 1: Write the script**

Create `backend/scripts/bootstrap_s3.sh`:

```bash
#!/usr/bin/env bash
#
# Bootstrap the nuprop-proposal-assets bucket. Idempotent — re-running it is
# safe; existing bucket / policy / lifecycle are left alone (head check first).
#
# Usage:
#   AWS_PROFILE=nuprop bash backend/scripts/bootstrap_s3.sh
#
# Requires: awscli v2, jq.

set -euo pipefail

BUCKET="${BUCKET:-nuprop-proposal-assets}"
REGION="${AWS_REGION:-ap-northeast-1}"

echo "==> Bootstrapping s3://${BUCKET} in ${REGION}"

# 1. Create bucket if it doesn't exist.
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
    echo "    bucket already exists, skipping create"
else
    echo "    creating bucket"
    aws s3api create-bucket \
        --bucket "${BUCKET}" \
        --region "${REGION}" \
        --create-bucket-configuration "LocationConstraint=${REGION}"
fi

# 2. Block all public access (defense-in-depth; assets are presigned-URL only).
echo "==> Blocking public access"
aws s3api put-public-access-block \
    --bucket "${BUCKET}" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. CORS — allow PUT (uploads) and GET (browser <img>/<video> playback) from
#    the production + local-dev origins. Header ETag exposed for upload
#    verification.
echo "==> Setting CORS"
aws s3api put-bucket-cors --bucket "${BUCKET}" --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://nuprop.fly.dev", "http://localhost:5173"],
      "AllowedMethods": ["GET", "PUT", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}'

# 4. Lifecycle — expire un-tagged objects after 90 days. S12 will tag
#    assets that belong to a published proposal so they survive.
echo "==> Setting lifecycle (90-day expiry on un-tagged objects)"
aws s3api put-bucket-lifecycle-configuration --bucket "${BUCKET}" --lifecycle-configuration '{
  "Rules": [
    {
      "ID": "expire-unpublished-after-90d",
      "Status": "Enabled",
      "Filter": {
        "Tag": {"Key": "published", "Value": "false"}
      },
      "Expiration": {"Days": 90}
    },
    {
      "ID": "default-expire-untagged-after-90d",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Expiration": {"Days": 90},
      "NoncurrentVersionExpiration": {"NoncurrentDays": 1}
    }
  ]
}'

echo "==> Done. Bucket ready: s3://${BUCKET}"
```

Make it executable:

```bash
chmod +x backend/scripts/bootstrap_s3.sh
```

- [ ] **Step 2: Confirm the script lints cleanly (no shellcheck errors)**

Run: `command -v shellcheck >/dev/null && shellcheck backend/scripts/bootstrap_s3.sh || echo "shellcheck not installed — skipping"`
Expected: either no output (clean) or the skip message.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/bootstrap_s3.sh
git commit -m "ops(S10): bootstrap script for nuprop-proposal-assets S3 bucket"
```

**Note for the executor:** running this script and pushing `FAL_KEY` to Fly are operator actions called out in the handoff (Task 16). The plan is internally complete without them; tests don't require either.

---

### Task 11: Frontend API hooks for the four asset endpoints

**Files:**
- Modify: `frontend/src/api/proposals.ts`

- [ ] **Step 1: Add the four hooks at the bottom of `proposals.ts`**

Append to `frontend/src/api/proposals.ts`:

```typescript
export interface PresignedUpload {
  upload_url: string
  s3_key: string
  asset_id: string
}

export function usePresignAsset(proposalId: string) {
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      kind: 'image' | 'video' | 'audio'
      filename: string
      content_type: string
      size: number
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<PresignedUpload>(
        `/proposals/${proposalId}/sections/${type}/assets/presign`,
        body,
      )
      return data
    },
  })
}

export function useCommitAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      asset_id: string
      s3_key: string
      kind: 'image' | 'video' | 'audio'
      content_type: string
      caption: string | null
      width: number | null
      height: number | null
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<SectionAsset>(
        `/proposals/${proposalId}/sections/${type}/assets/commit`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useGenerateAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      kind: 'image' | 'video' | 'audio'
      prompt: string
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<SectionAsset>(
        `/proposals/${proposalId}/sections/${type}/assets/generate`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useDeleteAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { type: SectionType; asset_id: string }) => {
      await api.delete(
        `/proposals/${proposalId}/sections/${vars.type}/assets/${vars.asset_id}`,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}
```

At the top of the file, extend the import line that pulls `Section` and `SectionType` so it also imports `SectionAsset`:

```typescript
import type {
  Proposal,
  ProposalCreate,
  ProposalListItem,
  ChatMessage,
  Section,
  SectionAsset,
  SectionType,
} from '../types/proposal'
```

- [ ] **Step 2: Re-run the existing api tests to make sure nothing regressed**

Run: `cd frontend && pnpm test -- src/api/__tests__/proposals.test.ts 2>&1 | tail -20`
Expected: PASS — existing tests unaffected (the new hooks have no callers yet).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/proposals.ts
git commit -m "feat(S10): frontend hooks for presign/commit/generate/delete asset"
```

---

### Task 12: AssetRow component — thumbnails with caption + delete

**Files:**
- Create: `frontend/src/components/sections/asset-row.tsx`
- Create: `frontend/src/components/sections/__tests__/asset-row.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/sections/__tests__/asset-row.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AssetRow } from '../asset-row'
import type { SectionAsset } from '../../../types/proposal'

const ASSETS: SectionAsset[] = [
  {
    id: 'a1',
    kind: 'image',
    s3_key: 'agency-1/p1/a1.png',
    url: 'https://s3.example/agency-1/p1/a1.png?signed=test',
    caption: 'hero shot',
    ai_generated: false,
  },
  {
    id: 'a2',
    kind: 'image',
    s3_key: 'agency-1/p1/a2.png',
    url: 'https://s3.example/agency-1/p1/a2.png?signed=test',
    caption: null,
    ai_generated: true,
    prompt: 'an astronaut',
    provider: 'fal-ai/nano-banana',
  },
]

describe('AssetRow', () => {
  it('renders one thumbnail per asset', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0]).toHaveAttribute('src', ASSETS[0].url)
    expect(imgs[1]).toHaveAttribute('src', ASSETS[1].url)
  })

  it('shows captions when present', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    expect(screen.getByText('hero shot')).toBeInTheDocument()
  })

  it('marks AI-generated assets', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    expect(screen.getAllByText(/AI/i).length).toBeGreaterThan(0)
  })

  it('renders nothing for an empty assets array', () => {
    const { container } = renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={[]} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('clicking delete sends the DELETE request', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.delete(`${API}/proposals/p1/sections/problem_statement/assets/a1`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    await user.click(screen.getAllByRole('button', { name: /delete asset/i })[0])
    await waitFor(() => expect(deleted).toBe(true))
  })
})
```

- [ ] **Step 2: Run to confirm they fail**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/asset-row.test.tsx 2>&1 | tail -15`
Expected: FAIL — `Cannot find module '../asset-row'`.

- [ ] **Step 3: Implement `AssetRow`**

Create `frontend/src/components/sections/asset-row.tsx`:

```typescript
import { useDeleteAsset } from '../../api/proposals'
import type { SectionAsset, SectionType } from '../../types/proposal'

interface Props {
  proposalId: string
  type: SectionType
  assets: SectionAsset[]
}

export function AssetRow({ proposalId, type, assets }: Props) {
  const del = useDeleteAsset(proposalId)

  if (assets.length === 0) return null

  return (
    <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {assets.map((a) => (
        <li
          key={a.id}
          className="group relative overflow-hidden rounded-md border border-stone-200 bg-stone-50"
        >
          <div className="aspect-video w-full bg-stone-100">
            <img
              src={a.url ?? ''}
              alt={a.caption ?? a.prompt ?? `Asset ${a.id}`}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="flex items-center justify-between gap-2 px-2 py-1 text-xs">
            <span className="truncate text-stone-600">
              {a.caption ?? (a.ai_generated ? `AI · ${a.prompt ?? ''}` : 'Uploaded')}
            </span>
            <button
              type="button"
              aria-label={`Delete asset ${a.id}`}
              onClick={() => del.mutate({ type, asset_id: a.id })}
              className="text-stone-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
          {a.ai_generated ? (
            <span className="absolute right-1 top-1 rounded bg-stone-900/70 px-1 text-[10px] uppercase tracking-wide text-white">
              AI
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/asset-row.test.tsx 2>&1 | tail -15`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sections/asset-row.tsx frontend/src/components/sections/__tests__/asset-row.test.tsx
git commit -m "feat(S10): AssetRow component — thumbnails with caption + delete"
```

---

### Task 13: AddImageMenu component — Upload or Generate

**Files:**
- Create: `frontend/src/components/sections/add-image-menu.tsx`
- Create: `frontend/src/components/sections/__tests__/add-image-menu.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/sections/__tests__/add-image-menu.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AddImageMenu } from '../add-image-menu'

const SAMPLE_FILE = new File(['fakebytes'], 'hero.png', { type: 'image/png' })

describe('AddImageMenu', () => {
  it('upload path: presign → PUT → commit', async () => {
    const user = userEvent.setup()
    const calls: { presign?: any; put?: any; commit?: any } = {}

    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/presign`,
        async ({ request }) => {
          calls.presign = await request.json()
          return HttpResponse.json({
            upload_url: 'https://s3.example/agency-1/p1/asset-1.png?upload=test',
            s3_key: 'agency-1/p1/asset-1.png',
            asset_id: 'asset-1',
          })
        },
      ),
      http.put('https://s3.example/agency-1/p1/asset-1.png', async ({ request }) => {
        calls.put = { method: request.method, contentType: request.headers.get('content-type') }
        return new HttpResponse(null, { status: 200 })
      }),
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/commit`,
        async ({ request }) => {
          calls.commit = await request.json()
          return HttpResponse.json({
            id: 'asset-1',
            kind: 'image',
            s3_key: 'agency-1/p1/asset-1.png',
            url: 'https://s3.example/agency-1/p1/asset-1.png?signed=ok',
            caption: null,
            ai_generated: false,
          })
        },
      ),
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    const fileInput = screen.getByLabelText(/upload file/i) as HTMLInputElement
    await user.upload(fileInput, SAMPLE_FILE)

    await waitFor(() => expect(calls.presign).toBeTruthy())
    expect(calls.presign).toEqual({
      kind: 'image',
      filename: 'hero.png',
      content_type: 'image/png',
      size: SAMPLE_FILE.size,
    })

    await waitFor(() => expect(calls.put?.contentType).toBe('image/png'))

    await waitFor(() => expect(calls.commit).toMatchObject({
      asset_id: 'asset-1',
      s3_key: 'agency-1/p1/asset-1.png',
      kind: 'image',
      content_type: 'image/png',
    }))
  })

  it('generate path: prompt → POST /generate', async () => {
    const user = userEvent.setup()
    let captured: any = null
    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/generate`,
        async ({ request }) => {
          captured = await request.json()
          return HttpResponse.json({
            id: 'ai-asset-1',
            kind: 'image',
            s3_key: 'agency-1/p1/ai-asset-1.png',
            url: 'https://s3.example/...?signed=ai',
            caption: null,
            ai_generated: true,
            prompt: 'an astronaut',
            provider: 'fal-ai/nano-banana',
          })
        },
      ),
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    await user.click(screen.getByRole('button', { name: /generate with ai/i }))
    const promptField = screen.getByLabelText(/image prompt/i)
    await user.type(promptField, 'an astronaut')
    await user.click(screen.getByRole('button', { name: /^generate$/i }))

    await waitFor(() => expect(captured).toEqual({ kind: 'image', prompt: 'an astronaut' }))
  })

  it('upload rejects an oversize file before calling presign', async () => {
    const user = userEvent.setup()
    let presigned = false
    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/presign`,
        () => {
          presigned = true
          return HttpResponse.json({})
        },
      ),
    )

    const big = new File(
      [new Uint8Array(11 * 1024 * 1024)],
      'big.png',
      { type: 'image/png' },
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    const fileInput = screen.getByLabelText(/upload file/i) as HTMLInputElement
    await user.upload(fileInput, big)

    await screen.findByText(/exceeds 10 mb/i)
    expect(presigned).toBe(false)
  })

})
```

- [ ] **Step 2: Run to confirm they fail**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/add-image-menu.test.tsx 2>&1 | tail -15`
Expected: FAIL — `Cannot find module '../add-image-menu'`.

- [ ] **Step 3: Implement `AddImageMenu`**

Create `frontend/src/components/sections/add-image-menu.tsx`:

```typescript
import axios from 'axios'
import { useRef, useState } from 'react'
import {
  useCommitAsset,
  useGenerateAsset,
  usePresignAsset,
} from '../../api/proposals'
import type { SectionType } from '../../types/proposal'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024  // 10 MB — backend will also reject

interface Props {
  proposalId: string
  type: SectionType
}

export function AddImageMenu({ proposalId, type }: Props) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'idle' | 'generate'>('idle')
  const [prompt, setPrompt] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const presign = usePresignAsset(proposalId)
  const commit = useCommitAsset(proposalId)
  const generate = useGenerateAsset(proposalId)

  const reset = () => {
    setOpen(false)
    setMode('idle')
    setPrompt('')
    setError(null)
  }

  const onPickFile = () => fileRef.current?.click()

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setError(null)

    if (f.size > MAX_IMAGE_BYTES) {
      setError('File exceeds 10 MB.')
      e.target.value = ''
      return
    }

    try {
      const presigned = await presign.mutateAsync({
        type,
        kind: 'image',
        filename: f.name,
        content_type: f.type || 'image/png',
        size: f.size,
      })

      // Upload directly to S3 — bypass our backend.
      await axios.put(presigned.upload_url, f, {
        headers: { 'Content-Type': f.type || 'image/png' },
      })

      // Read dimensions before commit so the editor can use them.
      const dims = await readImageDimensions(f).catch(() => ({ width: null, height: null }))

      await commit.mutateAsync({
        type,
        asset_id: presigned.asset_id,
        s3_key: presigned.s3_key,
        kind: 'image',
        content_type: f.type || 'image/png',
        caption: null,
        width: dims.width,
        height: dims.height,
      })

      reset()
    } catch (err) {
      setError('Upload failed. Try again.')
      // eslint-disable-next-line no-console
      console.error(err)
    } finally {
      if (e.target) e.target.value = ''
    }
  }

  const onGenerate = async () => {
    if (!prompt.trim()) return
    setError(null)
    try {
      await generate.mutateAsync({ type, kind: 'image', prompt: prompt.trim() })
      reset()
    } catch (err) {
      setError('Generation failed. Try again.')
      // eslint-disable-next-line no-console
      console.error(err)
    }
  }

  return (
    <div className="relative mt-3 inline-block">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        className="rounded-md border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50"
      >
        + Add image
      </button>

      {open && mode === 'idle' && (
        <div className="absolute left-0 z-10 mt-1 w-52 rounded-md border border-stone-200 bg-white p-1 shadow-lg">
          <label
            htmlFor={`upload-${type}`}
            className="block cursor-pointer rounded px-3 py-2 text-xs text-stone-700 hover:bg-stone-100"
            onClick={onPickFile}
          >
            Upload file
          </label>
          <input
            id={`upload-${type}`}
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="sr-only"
            onChange={onFileChange}
          />
          <button
            type="button"
            onClick={() => setMode('generate')}
            className="block w-full rounded px-3 py-2 text-left text-xs text-stone-700 hover:bg-stone-100"
          >
            Generate with AI
          </button>
        </div>
      )}

      {open && mode === 'generate' && (
        <div className="absolute left-0 z-10 mt-1 w-72 rounded-md border border-stone-200 bg-white p-3 shadow-lg">
          <label htmlFor={`prompt-${type}`} className="block text-xs font-medium text-stone-700">
            Image prompt
          </label>
          <textarea
            id={`prompt-${type}`}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded border border-stone-200 p-2 text-xs"
          />
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={reset}
              className="rounded px-2 py-1 text-xs text-stone-600 hover:bg-stone-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onGenerate}
              disabled={generate.isPending || !prompt.trim()}
              className="rounded bg-stone-900 px-3 py-1 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {generate.isPending ? 'Generating…' : 'Generate'}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-1 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}


function readImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/add-image-menu.test.tsx 2>&1 | tail -15`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sections/add-image-menu.tsx frontend/src/components/sections/__tests__/add-image-menu.test.tsx
git commit -m "feat(S10): AddImageMenu — upload-or-generate split button"
```

---

### Task 14: Wire AssetRow + AddImageMenu into SectionBlock

**Files:**
- Modify: `frontend/src/components/sections/section-block.tsx`
- Modify: `frontend/src/components/sections/__tests__/section-block.test.tsx`

- [ ] **Step 1: Write the additional failing tests**

Append to `frontend/src/components/sections/__tests__/section-block.test.tsx` inside the existing `describe('SectionBlock', ...)` block:

```typescript
  it('renders the asset row when section has assets', () => {
    const withAssets = {
      ...SAMPLE,
      assets: [
        {
          id: 'a1',
          kind: 'image' as const,
          s3_key: 'agency-1/p1/a1.png',
          url: 'https://s3.example/agency-1/p1/a1.png?signed=t',
          caption: 'hero',
          ai_generated: false,
        },
      ],
    }
    renderWithProviders(
      <SectionBlock
        proposalId="p1"
        type="problem_statement"
        title="Problem statement"
        section={withAssets}
      />,
    )
    expect(screen.getByRole('img')).toBeInTheDocument()
  })

  it('renders the add-image menu', () => {
    renderWithProviders(
      <SectionBlock
        proposalId="p1"
        type="problem_statement"
        title="Problem statement"
        section={SAMPLE}
      />,
    )
    expect(screen.getByRole('button', { name: /add image/i })).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run to confirm they fail**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/section-block.test.tsx 2>&1 | tail -15`
Expected: FAIL — both new tests fail (no AssetRow / AddImageMenu rendered).

- [ ] **Step 3: Wire the components into `section-block.tsx`**

Modify `frontend/src/components/sections/section-block.tsx`. After the existing imports, add:

```typescript
import { AssetRow } from './asset-row'
import { AddImageMenu } from './add-image-menu'
```

Inside the `return (...)`, replace the trailing `<div className="mt-3">` (the toolbar wrapper) and its contents with:

```tsx
      {included && (
        <>
          <AssetRow proposalId={proposalId} type={type} assets={section.assets ?? []} />
          <AddImageMenu proposalId={proposalId} type={type} />
        </>
      )}

      <div className="mt-3">
        <SectionToolbar
          isRegenerating={regenerate.isPending}
          isRefining={refine.isPending}
          isIncluded={included}
          onRegenerate={onRegenerate}
          onRefine={onRefine}
          onToggleInclude={onToggleInclude}
        />
      </div>
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm test -- src/components/sections/__tests__/section-block.test.tsx 2>&1 | tail -15`
Expected: PASS — all section-block tests including the two new ones.

Also run the full frontend suite to catch regressions:

Run: `cd frontend && pnpm test 2>&1 | tail -10`
Expected: PASS — full count is `265 + ~9 = ~274` (5 asset-row + 4 add-image-menu + previous 265 with +2 section-block tests means roughly +11 net).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sections/section-block.tsx frontend/src/components/sections/__tests__/section-block.test.tsx
git commit -m "feat(S10): mount AssetRow + AddImageMenu inside each section block"
```

---

### Task 15: Full-suite regression

**Files:** none (verification only)

- [ ] **Step 1: Backend full suite**

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -10`
Expected: PASS — count is `406 → ~439` (+10 media-common, +7 section-assets, +4 image-gen, +11 asset-endpoints, +1 resign-on-GET = 33 new tests, no replacements).

If anything regressed: stop and investigate before continuing. Common suspects:
- The `_no_network` extension might over-block a presign call in a non-asset test — narrow it if so.
- The viewmodel re-sign might double-sign a section dict that was already serialized.

- [ ] **Step 2: Frontend full suite**

Run: `cd frontend && pnpm test 2>&1 | tail -10`
Expected: PASS — `265 → ~275` (+5 asset-row, +3 add-image-menu, +2 section-block integration).

- [ ] **Step 3: Confirm alembic head unchanged**

Run: `cd backend && .venv/bin/python -m alembic heads`
Expected: `05_proposal_section_columns (head)`. **S10 ships no schema migration.**

- [ ] **Step 4: No commit on this task** — verification-only.

---

### Task 16: Handoff + deploy prep

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`

- [ ] **Step 1: Add the new "What happened this session" block to `docs/superpowers/HANDOFF.md`**

Insert (immediately under the existing `## What happened this session (2026-05-26 — S9)` section header — the S10 block goes *above* the S9 block so the most recent is first):

```markdown
## What happened this session (2026-05-27 — S10)

Shipped **S10 — image media (upload + Nano Banana generation)**, the second slice of the S9-S13 section-redesign roadmap.

### Architecture

- **S3 bucket `nuprop-proposal-assets`** in `ap-northeast-1` — private, block-public-access on, CORS allows PUT/GET/HEAD from `https://nuprop.fly.dev` and `http://localhost:5173`, 90-day lifecycle on objects tagged `published=false` (S12 will tag survivors). Provisioned via `backend/scripts/bootstrap_s3.sh`.
- **New media service package** at `backend/app/services/media/`: `_common.py` (kinds, mime/size caps, key shape, `Asset` TypedDict, `validate_upload`), `_s3.py` (cached boto3 client; presigned PUT 15min / GET 1h; async-offloaded upload/delete), `_fal.py` (async fal.ai wrapper — the single seam tests monkeypatch), `image_gen.py` (Nano Banana → httpx download → S3 → `Asset`), `section_assets.py` (pure helpers: append/remove/resign).
- **Four section-scoped asset endpoints** under `/api/v1/proposals/{id}/sections/{type}/assets/...`: `presign` (returns `{upload_url, s3_key, asset_id}`), `commit` (records the uploaded asset on the section), `generate` (kind=image only in S10; S11 widens to video+audio), `delete` (removes from section + S3).
- **Re-sign on read.** `GET /proposals/{id}` walks every section's `assets[]` and rewrites `url` from the canonical `s3_key`. Persisted URLs never trusted past 1h.
- **Frontend:** new `AssetRow` (thumbnail grid + delete) and `AddImageMenu` (split-button: Upload file / Generate with AI) live under each `SectionBlock`. Uploads go presign → direct browser PUT to S3 → commit (no bytes through Python).

### Test counts

- Backend: `406 → ~439` (+10 media-common, +7 section-assets, +4 image-gen, +11 asset endpoints incl IDOR, +1 re-sign-on-GET).
- Frontend: `265 → ~275` (+5 asset-row, +3 add-image-menu, +2 section-block integration).
- Migration head: `05_proposal_section_columns` (no schema change in S10).

### Non-goals carried forward to S11+

- Video + audio kinds — S11 widens `/assets/generate` and adds `+ Add video` / `+ Add audio` menus.
- Video first-frame poster — optional in S11 spec.
- `published` tagging on Publish — S12.
- NUSTAGE pull via `GET /export?token=…` — S12.

### Operator steps needed before merge

1. **Provision the bucket:** `AWS_PROFILE=nuprop bash backend/scripts/bootstrap_s3.sh` (idempotent; head-check first).
2. **Push `FAL_KEY` to Fly:** `fly secrets set -a nuprop FAL_KEY="<key>"`. Get the key from https://fal.ai/dashboard. The app boots without it but `/generate` will 500 until the secret is set.
3. **Verify the bucket region matches `AWS_REGION` (`ap-northeast-1`)** — Fly's app pool already has IAM creds with `s3:PutObject` / `s3:GetObject` / `s3:DeleteObject` on the bucket prefix. If not, attach a minimal policy at `arn:aws:s3:::nuprop-proposal-assets/*`.
```

Update the top block of the file to reflect the new HEAD:

```markdown
**Last updated:** 2026-05-27 (S10 image media shipped)
**Latest commit on `main`:** `<merge commit>` (S10 merge). Pushed; auto-deploy run triggered.
```

(The actual hash gets filled in at merge time by `superpowers:finishing-a-development-branch`.)

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S10): mark S10 image-media complete"
```

---

## Acceptance checklist (before requesting review)

- [ ] All 16 tasks committed, in order, on a branch named like `worktree-s10-image-media`.
- [ ] Backend full suite passes (`~439` tests, no skips beyond the existing ones).
- [ ] Frontend full suite passes (`≥ 275` tests).
- [ ] `alembic heads` shows `05_proposal_section_columns` (no new migration).
- [ ] `backend/scripts/bootstrap_s3.sh` is executable and shellcheck-clean.
- [ ] `HANDOFF.md` has the S10 block on top with operator steps called out.
- [ ] No new imports of `fal_client` outside `backend/app/services/media/_fal.py`.
- [ ] No direct `boto3.client("s3")` calls outside `backend/app/services/media/_s3.py`.
- [ ] No bytes pass through Python on the upload path — only presign + commit.
- [ ] Asset URLs in `GET /proposals/{id}` responses match the `https://s3.example/{key}?signed=test` pattern in tests (proves the re-sign hook is wired).
