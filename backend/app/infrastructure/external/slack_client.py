from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings


class SlackClient:
    """Slack OAuth + API via httpx. Searches for client mentions in workspace."""

    OAUTH_AUTH_URL = "https://slack.com/oauth/v2/authorize"
    OAUTH_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
    API_BASE = "https://slack.com/api"
    SCOPES = "search:read,channels:history,channels:read"

    def __init__(self):
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.SLACK_CLIENT_ID and self._settings.SLACK_CLIENT_SECRET)

    # ── OAuth ────────────────────────────────────────────────

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self._settings.SLACK_CLIENT_ID,
            "scope": self.SCOPES,
            "redirect_uri": self._settings.SLACK_REDIRECT_URI,
            "state": state,
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(self.OAUTH_TOKEN_URL, data={
                "code": code,
                "client_id": self._settings.SLACK_CLIENT_ID,
                "client_secret": self._settings.SLACK_CLIENT_SECRET,
                "redirect_uri": self._settings.SLACK_REDIRECT_URI,
            })
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise ValueError(data.get("error", "Slack OAuth failed"))
            return data

    # ── Search ───────────────────────────────────────────────

    async def search_messages(
        self, access_token: str, query: str, count: int = 20,
    ) -> list[dict]:
        """Search workspace messages mentioning the query (client name)."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.API_BASE}/search.messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"query": query, "count": count, "sort": "timestamp", "sort_dir": "desc"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                return []

        messages = data.get("messages", {}).get("matches", [])
        results = []
        for m in messages:
            results.append({
                "text": m.get("text", "")[:500],
                "user": m.get("username", ""),
                "channel": m.get("channel", {}).get("name", ""),
                "timestamp": m.get("ts", ""),
                "permalink": m.get("permalink", ""),
                "is_internal": not m.get("channel", {}).get("is_shared", False),
            })
        return results

    async def get_workspace_info(self, access_token: str) -> dict:
        """Get workspace name and team info."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.API_BASE}/team.info",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                return {}
            team = data.get("team", {})
            return {"name": team.get("name", ""), "domain": team.get("domain", "")}
