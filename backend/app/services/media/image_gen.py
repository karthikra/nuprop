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
