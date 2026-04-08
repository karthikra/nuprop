from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings


class GCalClient:
    """Google Calendar API v3 via httpx. Extracts meeting patterns with clients."""

    CAL_API = "https://www.googleapis.com/calendar/v3"
    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

    def __init__(self):
        self._settings = get_settings()

    async def search_events(
        self, access_token: str, query: str, months_back: int = 12, max_results: int = 50,
    ) -> list[dict]:
        """Search calendar events matching a query (client name). Returns event list."""
        time_min = (datetime.now(timezone.utc) - timedelta(days=months_back * 30)).isoformat()

        params = {
            "q": query,
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.CAL_API}/calendars/primary/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("items", [])

    async def get_client_meeting_stats(
        self, access_token: str, client_name: str, months_back: int = 12,
    ) -> dict:
        """Analyze meeting patterns with a client. Returns stats dict."""
        events = await self.search_events(access_token, client_name, months_back)

        if not events:
            return {
                "meeting_count": 0,
                "frequency": "none",
                "last_meeting": None,
                "attendees": [],
                "topics": [],
            }

        # Extract meeting data
        meetings = []
        all_attendees: dict[str, int] = {}
        topics = []

        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
            summary = event.get("summary", "")
            attendees = event.get("attendees", [])

            meetings.append({"date": start, "summary": summary})
            topics.append(summary)

            for a in attendees:
                email = a.get("email", "")
                name = a.get("displayName", email)
                if email and "calendar.google.com" not in email:
                    all_attendees[name] = all_attendees.get(name, 0) + 1

        # Calculate frequency
        count = len(meetings)
        if count >= 12:
            frequency = "weekly"
        elif count >= 4:
            frequency = "monthly"
        elif count >= 2:
            frequency = "quarterly"
        else:
            frequency = "occasional"

        # Top attendees
        top_attendees = sorted(all_attendees.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "meeting_count": count,
            "frequency": frequency,
            "months_analyzed": months_back,
            "last_meeting": meetings[-1]["date"] if meetings else None,
            "first_meeting": meetings[0]["date"] if meetings else None,
            "attendees": [{"name": name, "meetings": n} for name, n in top_attendees],
            "recent_topics": topics[-5:] if topics else [],
        }
