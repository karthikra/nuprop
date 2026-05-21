from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GmailClient:
    """Google OAuth 2.0 + Gmail API v1 via raw HTTP (no Google SDK)."""

    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self):
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.GOOGLE_CLIENT_ID and self._settings.GOOGLE_CLIENT_SECRET)

    # ── OAuth ────────────────────────────────────────────────

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
            "scope": " ".join(self.SCOPES),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(self.OAUTH_TOKEN_URL, data={
                "code": code,
                "client_id": self._settings.GOOGLE_CLIENT_ID,
                "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            })
            r.raise_for_status()
            return r.json()

    async def refresh_access_token(self, refresh_token: str) -> str:
        async with httpx.AsyncClient() as client:
            r = await client.post(self.OAUTH_TOKEN_URL, data={
                "refresh_token": refresh_token,
                "client_id": self._settings.GOOGLE_CLIENT_ID,
                "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            })
            r.raise_for_status()
            return r.json()["access_token"]

    async def get_user_email(self, access_token: str) -> str:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.GMAIL_API}/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r.raise_for_status()
            return r.json()["emailAddress"]

    async def revoke_token(self, token: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.OAUTH_REVOKE_URL, params={"token": token})
        except httpx.HTTPError as exc:
            logger.warning(
                "gmail token revoke failed (best-effort)",
                extra={"event": "connector.gmail.revoke_http_error", "error": str(exc)},
            )

    # ── Gmail Data ───────────────────────────────────────────

    async def search_messages(
        self, access_token: str, query: str, max_results: int = 100, page_token: str | None = None,
    ) -> tuple[list[dict], str | None]:
        params: dict = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.GMAIL_API}/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            r.raise_for_status()
            data = r.json()

        messages = data.get("messages", [])
        next_token = data.get("nextPageToken")
        return messages, next_token

    async def get_message(self, access_token: str, message_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.GMAIL_API}/users/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "To", "Subject", "Date"],
                },
            )
            r.raise_for_status()
            data = r.json()

        headers = {}
        for h in data.get("payload", {}).get("headers", []):
            headers[h["name"].lower()] = h["value"]

        has_attachments = any(
            part.get("filename") for part in data.get("payload", {}).get("parts", [])
        )

        date_str = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "gmail message date parse failed; defaulting to now()",
                extra={
                    "event": "connector.gmail.bad_date",
                    "raw": date_str[:40],
                    "error": str(exc),
                },
            )
            date = datetime.now()

        return {
            "id": data["id"],
            "thread_id": data.get("threadId", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "snippet": data.get("snippet", ""),
            "date": date,
            "has_attachments": has_attachments,
        }

    async def fetch_messages_for_domain(
        self, access_token: str, domain: str, since: datetime | None = None, limit: int = 200,
    ) -> list[dict]:
        query = f"from:{domain} OR to:{domain}"
        if since:
            query += f" after:{since.strftime('%Y/%m/%d')}"

        all_messages = []
        page_token = None

        while len(all_messages) < limit:
            batch_size = min(100, limit - len(all_messages))
            msg_refs, page_token = await self.search_messages(access_token, query, batch_size, page_token)

            for ref in msg_refs:
                try:
                    msg = await self.get_message(access_token, ref["id"])
                    all_messages.append(msg)
                except (httpx.HTTPError, KeyError) as exc:
                    logger.warning(
                        "gmail get_message failed for one ref; skipping",
                        extra={
                            "event": "connector.gmail.message_fetch_failed",
                            "ref_id": ref.get("id"),
                            "error": str(exc),
                        },
                    )
                    continue

            if not page_token:
                break

        return all_messages

    async def fetch_recent_messages(
        self,
        access_token: str,
        lookback_days: int,
        limit: int,
    ) -> list[dict]:
        """Fetch up to `limit` recent messages from the last `lookback_days`.

        No domain filter -- caller filters/aggregates downstream. Uses the same
        log-and-skip pattern as fetch_messages_for_domain for individual
        get_message failures.
        """
        from datetime import timedelta

        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        query = f"after:{since.strftime('%Y/%m/%d')}"

        all_messages: list[dict] = []
        page_token: str | None = None

        while len(all_messages) < limit:
            batch_size = min(100, limit - len(all_messages))
            msg_refs, page_token = await self.search_messages(
                access_token, query, batch_size, page_token,
            )

            for ref in msg_refs:
                if len(all_messages) >= limit:
                    break
                try:
                    msg = await self.get_message(access_token, ref["id"])
                    all_messages.append(msg)
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    logger.warning(
                        "gmail get_message failed during discovery scan; skipping",
                        extra={
                            "event": "connector.gmail.discovery_message_fetch_failed",
                            "ref_id": ref.get("id"),
                            "error": str(exc),
                        },
                    )
                    continue

            if not page_token:
                break

        return all_messages
