"""Redis pub/sub bridge for WebSocket events.

The worker runs in a separate process and cannot reach the API process's
in-memory ``ws_manager``. Every WS emit is published to the ``nuprop:ws`` Redis
channel; the API process runs ``ws_event_subscriber`` (started in lifespan) which
relays each event to its locally-held WebSocket connections.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

WS_CHANNEL = "nuprop:ws"


async def publish(redis, proposal_id: str, payload: dict) -> None:
    """Publish a WebSocket event for a proposal onto the shared Redis channel.

    ``redis`` is any redis client with an async ``publish`` — the ARQ pool in the
    API process, or ``ctx['redis']`` in a worker task.
    """
    envelope = json.dumps({"proposal_id": str(proposal_id), "payload": payload})
    await redis.publish(WS_CHANNEL, envelope)


async def _handle_event(raw: str | bytes) -> None:
    """Relay one received pub/sub message to the local ws_manager."""
    try:
        envelope = json.loads(raw)
        proposal_id = envelope["proposal_id"]
        payload = envelope["payload"]
    except (ValueError, KeyError, TypeError):
        logger.warning("dropping malformed ws event: %r", raw)
        return
    await ws_manager.broadcast(proposal_id, payload)


async def ws_event_subscriber() -> None:
    """Long-lived task: subscribe to the WS channel and relay to ws_manager.

    Started as an asyncio task in ``app.main`` lifespan. Reconnects on error.
    """
    while True:
        client = aioredis.from_url(get_settings().REDIS_URL)
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(WS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    await _handle_event(message["data"])
        except asyncio.CancelledError:
            await client.aclose()
            raise
        except Exception:  # noqa: BLE001 — keep the subscriber alive
            logger.exception("ws subscriber error; reconnecting in 2s")
            await client.aclose()
            await asyncio.sleep(2)
