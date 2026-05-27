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
