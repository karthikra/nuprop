# S6 — Connector Resilience & Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four connector HTTP clients resilient to transient provider failures via a shared retry/backoff wrapper, and close the remaining audit-flagged backend hardening items (gmail pagination cap, email parsing, LLM timeout, `client_repo` cap).

**Architecture:** A single new module `app/infrastructure/external/_retry.py` owns the whole retry policy. Each of the four connector clients (`gmail_client`, `gdrive_client`, `gcal_client`, `slack_client`) replaces its inline `httpx.AsyncClient()` blocks with a `request_with_retry(...)` call — no signature or return-type changes, so the connector viewmodel is untouched. Four small standalone fixes follow. No schema change; migration head stays `03_proposal_context_brief`.

**Tech Stack:** Python 3.14, `httpx` (async), `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`), SQLAlchemy async, `AsyncAnthropicBedrock`.

**Spec:** `docs/superpowers/specs/2026-05-22-s6-connector-resilience-design.md`

**Working directory:** all paths below are relative to `backend/`. Run all commands from `backend/`.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `app/infrastructure/external/_retry.py` | The single retry/backoff policy: `request_with_retry`, backoff + `Retry-After` helpers | Create |
| `app/infrastructure/external/gmail_client.py` | Gmail OAuth + API; gains retry, pagination cap, `None`-date fix | Modify |
| `app/infrastructure/external/gdrive_client.py` | Drive API; gains retry | Modify |
| `app/infrastructure/external/gcal_client.py` | Calendar API; gains retry | Modify |
| `app/infrastructure/external/slack_client.py` | Slack OAuth + search; gains retry | Modify |
| `app/viewmodels/connector_viewmodel.py` | `_extract_domains` gains an `@` guard | Modify |
| `app/services/llm.py` | `AIService` gains a Bedrock client timeout | Modify |
| `app/infrastructure/db/repositories/client_repo.py` | `search` default `limit` 50 → 500 | Modify |
| `tests/unit/test_retry.py` | Retry wrapper unit tests | Create |
| `tests/unit/test_connector_clients_retry.py` | Wiring tests: clients route through `request_with_retry` | Create |
| `tests/unit/test_gmail_client_hardening.py` | Pagination cap + `None`-date tests | Create |
| `tests/unit/test_extract_domains.py` | `_extract_domains` `@`-guard test | Create |
| `tests/unit/test_llm_timeout.py` | `AIService` Bedrock timeout test | Create |
| `tests/unit/test_client_repo_limit.py` | `client_repo` default-limit test | Create |

---

### Task 1: Retry wrapper module

**Files:**
- Create: `app/infrastructure/external/_retry.py`
- Test: `tests/unit/test_retry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_retry.py`:

```python
from __future__ import annotations

import httpx
import pytest

from app.infrastructure.external import _retry
from app.infrastructure.external._retry import request_with_retry


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make backoff instant so retry tests don't actually wait."""

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(_retry, "_sleep", _instant)


def _counting_handler(script):
    """httpx.MockTransport handler yielding `script` entries in order.
    Each entry is an int status, a (status, headers) tuple, or an Exception
    to raise. The last entry repeats once the script is exhausted."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        item = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            status, headers = item
            return httpx.Response(status, headers=headers)
        return httpx.Response(item)

    return handler, calls


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    handler, calls = _counting_handler([429, 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_does_not_retry_on_401():
    handler, calls = _counting_handler([401, 200])
    with pytest.raises(httpx.HTTPStatusError):
        await request_with_retry(
            "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
        )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_raises_after_exhausting_attempts_on_503():
    handler, calls = _counting_handler([503])
    with pytest.raises(httpx.HTTPStatusError):
        await request_with_retry(
            "GET", "https://x.test/y",
            transport=httpx.MockTransport(handler), max_attempts=3,
        )
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retries_on_transport_error():
    handler, calls = _counting_handler([httpx.ConnectError("boom"), 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_honors_retry_after_header(monkeypatch):
    seen: list[float] = []

    async def _record(seconds):
        seen.append(seconds)

    monkeypatch.setattr(_retry, "_sleep", _record)
    handler, _ = _counting_handler([(429, {"Retry-After": "7"}), 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert seen == [7.0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_retry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.external._retry'`

- [ ] **Step 3: Write the implementation**

Create `app/infrastructure/external/_retry.py`:

```python
"""Shared HTTP retry/backoff for the connector clients.

All four connector clients (Gmail, Drive, Calendar, Slack) route their
requests through ``request_with_retry`` so the retry policy lives in one
place. Retries 429/5xx and transport errors; never retries other 4xx —
a 401 ``invalid_grant`` must surface to the caller unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_ATTEMPTS = 4
_BACKOFF_BASE = 0.5
_BACKOFF_JITTER = 0.5

# Indirection so tests can stub out the actual waiting without touching the
# global asyncio.sleep.
_sleep = asyncio.sleep


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter. ``attempt`` is 1-based."""
    return _BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, _BACKOFF_JITTER)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honor a numeric ``Retry-After`` header; otherwise exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(int(retry_after))
        except ValueError:
            pass
    return _backoff(attempt)


async def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    transport: httpx.AsyncBaseTransport | None = None,
    **kwargs,
) -> httpx.Response:
    """Issue an HTTP request, retrying transient failures.

    Retries on 429/5xx and ``httpx.TransportError`` with exponential backoff
    (honoring ``Retry-After``). Raises ``httpx.HTTPStatusError`` on a
    non-retryable status, or on a 5xx that survives every attempt; raises the
    last ``httpx.TransportError`` if transport errors exhaust the attempts.

    ``transport`` is a test seam — production callers leave it ``None``.
    """
    last_transport_exc: httpx.TransportError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_transport_exc = exc
            if attempt >= max_attempts:
                break
            delay = _backoff(attempt)
            logger.warning(
                "connector http transport error; retrying",
                extra={
                    "event": "connector.retry",
                    "url": url,
                    "attempt": attempt,
                    "delay": round(delay, 2),
                    "error": str(exc),
                },
            )
            await _sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
            delay = _retry_delay(response, attempt)
            logger.warning(
                "connector http retryable status; retrying",
                extra={
                    "event": "connector.retry",
                    "url": url,
                    "status": response.status_code,
                    "attempt": attempt,
                    "delay": round(delay, 2),
                },
            )
            await _sleep(delay)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "connector http request failed",
                extra={
                    "event": "connector.retry.exhausted",
                    "url": url,
                    "status": response.status_code,
                    "attempts": attempt,
                },
            )
            raise
        return response

    logger.error(
        "connector http request exhausted retries",
        extra={"event": "connector.retry.exhausted", "url": url, "attempts": max_attempts},
    )
    assert last_transport_exc is not None
    raise last_transport_exc
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_retry.py -q`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/external/_retry.py tests/unit/test_retry.py
git commit -m "feat(S6): add shared connector HTTP retry/backoff wrapper"
```

---

### Task 2: Migrate gmail_client.py to the retry wrapper

**Files:**
- Modify: `app/infrastructure/external/gmail_client.py`
- Test: `tests/unit/test_connector_clients_retry.py` (created here, extended in Task 3)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_connector_clients_retry.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


@pytest.mark.asyncio
async def test_gmail_get_user_email_routes_through_retry_wrapper():
    client = GmailClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return SimpleNamespace(json=lambda: {"emailAddress": "me@acme.com"})

    with patch(
        "app.infrastructure.external.gmail_client.request_with_retry", new=fake_retry
    ):
        email = await client.get_user_email("tok")

    assert email == "me@acme.com"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/users/me/profile")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_connector_clients_retry.py -q`
Expected: FAIL — `AttributeError: ... does not have the attribute 'request_with_retry'` (the name is not yet imported into `gmail_client`).

- [ ] **Step 3: Migrate gmail_client.py**

In `app/infrastructure/external/gmail_client.py`, add the import after the existing `import httpx` (line 8):

```python
import httpx

from app.core.config import get_settings
from app.infrastructure.external._retry import request_with_retry
```

Replace the six HTTP methods. `exchange_code`:

```python
    async def exchange_code(self, code: str) -> dict:
        r = await request_with_retry("POST", self.OAUTH_TOKEN_URL, data={
            "code": code,
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        return r.json()
```

`refresh_access_token`:

```python
    async def refresh_access_token(self, refresh_token: str) -> str:
        r = await request_with_retry("POST", self.OAUTH_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        return r.json()["access_token"]
```

`get_user_email`:

```python
    async def get_user_email(self, access_token: str) -> str:
        r = await request_with_retry(
            "GET",
            f"{self.GMAIL_API}/users/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return r.json()["emailAddress"]
```

`revoke_token` (stays best-effort — `HTTPStatusError` and `TransportError` are both `httpx.HTTPError` subclasses, so the existing `except` still catches them):

```python
    async def revoke_token(self, token: str) -> None:
        try:
            await request_with_retry(
                "POST", self.OAUTH_REVOKE_URL, params={"token": token}
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "gmail token revoke failed (best-effort)",
                extra={"event": "connector.gmail.revoke_http_error", "error": str(exc)},
            )
```

`search_messages` (replace the `async with` block; keep the lines after it unchanged):

```python
    async def search_messages(
        self, access_token: str, query: str, max_results: int = 100, page_token: str | None = None,
    ) -> tuple[list[dict], str | None]:
        params: dict = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token

        r = await request_with_retry(
            "GET",
            f"{self.GMAIL_API}/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        data = r.json()

        messages = data.get("messages", [])
        next_token = data.get("nextPageToken")
        return messages, next_token
```

`get_message` (replace only the `async with` block at the top — the header/date/return code below stays as-is for now; Task 5 changes the date handling):

```python
    async def get_message(self, access_token: str, message_id: str) -> dict:
        r = await request_with_retry(
            "GET",
            f"{self.GMAIL_API}/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["From", "To", "Subject", "Date"],
            },
        )
        data = r.json()
```

Leave `import httpx` in place — it is still used by `revoke_token` and by the `except (httpx.HTTPError, ...)` clauses in the pagination loops.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_connector_clients_retry.py tests/unit/test_gmail_client_fetch_recent.py -q`
Expected: PASS — the new wiring test passes and the existing gmail fetch tests still pass (they patch `search_messages` / `get_message` directly, so they are unaffected by the transport change).

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/external/gmail_client.py tests/unit/test_connector_clients_retry.py
git commit -m "refactor(S6): route gmail_client through the retry wrapper"
```

---

### Task 3: Migrate gdrive_client, gcal_client, slack_client to the retry wrapper

**Files:**
- Modify: `app/infrastructure/external/gdrive_client.py`
- Modify: `app/infrastructure/external/gcal_client.py`
- Modify: `app/infrastructure/external/slack_client.py`
- Test: `tests/unit/test_connector_clients_retry.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_connector_clients_retry.py`:

```python
from app.infrastructure.external.gcal_client import GCalClient
from app.infrastructure.external.gdrive_client import GDriveClient
from app.infrastructure.external.slack_client import SlackClient


@pytest.mark.asyncio
async def test_gdrive_search_files_routes_through_retry_wrapper():
    client = GDriveClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(json=lambda: {"files": [{"id": "f1"}]})

    with patch(
        "app.infrastructure.external.gdrive_client.request_with_retry", new=fake_retry
    ):
        files = await client.search_files("tok", "acme")

    assert files == [{"id": "f1"}]
    assert captured["method"] == "GET"


@pytest.mark.asyncio
async def test_gcal_search_events_routes_through_retry_wrapper():
    client = GCalClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(json=lambda: {"items": [{"id": "e1"}]})

    with patch(
        "app.infrastructure.external.gcal_client.request_with_retry", new=fake_retry
    ):
        events = await client.search_events("tok", "acme")

    assert events == [{"id": "e1"}]
    assert captured["method"] == "GET"


@pytest.mark.asyncio
async def test_slack_search_messages_routes_through_retry_wrapper():
    client = SlackClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(
            json=lambda: {"ok": True, "messages": {"matches": []}}
        )

    with patch(
        "app.infrastructure.external.slack_client.request_with_retry", new=fake_retry
    ):
        results = await client.search_messages("tok", "acme")

    assert results == []
    assert captured["method"] == "GET"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_connector_clients_retry.py -q`
Expected: FAIL — the three new tests fail with `AttributeError: ... 'request_with_retry'` for the gdrive/gcal/slack modules.

- [ ] **Step 3a: Migrate gdrive_client.py**

In `app/infrastructure/external/gdrive_client.py`, add the import:

```python
import httpx

from app.core.config import get_settings
from app.infrastructure.external._retry import request_with_retry
```

Replace `search_files`:

```python
    async def search_files(
        self, access_token: str, query: str, max_results: int = 20,
    ) -> list[dict]:
        """Search Drive for files matching a query. Returns file metadata list."""
        params = {
            "q": f"fullText contains '{query}' and trashed = false",
            "pageSize": max_results,
            "fields": "files(id,name,mimeType,modifiedTime,owners,webViewLink,description)",
            "orderBy": "modifiedTime desc",
        }
        r = await request_with_retry(
            "GET",
            f"{self.DRIVE_API}/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        return r.json().get("files", [])
```

Replace the `async with` block inside `get_file_content_text` (keep the surrounding `try`/`except httpx.HTTPError`):

```python
    async def get_file_content_text(self, access_token: str, file_id: str) -> str:
        """Export a Google Doc/Sheet as plain text. For PDFs/DOCX, gets metadata only."""
        try:
            r = await request_with_retry(
                "GET",
                f"{self.DRIVE_API}/files/{file_id}/export",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"mimeType": "text/plain"},
                timeout=15,
            )
            return r.text[:5000]  # Cap at 5K chars
        except httpx.HTTPError as exc:
            logger.warning(
                "Drive document export failed; returning empty content",
                extra={"event": "connector.drive.export_failed", "error": str(exc)},
            )
            return ""
```

Leave `import httpx` in place — still used by the `except httpx.HTTPError` clause.

- [ ] **Step 3b: Migrate gcal_client.py**

In `app/infrastructure/external/gcal_client.py`, replace the `import httpx` line with the retry import (gcal has no other `httpx` reference once migrated):

```python
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.infrastructure.external._retry import request_with_retry
```

Replace the `async with` block inside `search_events`:

```python
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
        r = await request_with_retry(
            "GET",
            f"{self.CAL_API}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        return r.json().get("items", [])
```

- [ ] **Step 3c: Migrate slack_client.py**

In `app/infrastructure/external/slack_client.py`, replace the `import httpx` line (slack has no other `httpx` reference once migrated):

```python
from urllib.parse import urlencode

import logging

from app.core.config import get_settings
from app.infrastructure.external._retry import request_with_retry
```

Replace `exchange_code`:

```python
    async def exchange_code(self, code: str) -> dict:
        r = await request_with_retry("POST", self.OAUTH_TOKEN_URL, data={
            "code": code,
            "client_id": self._settings.SLACK_CLIENT_ID,
            "client_secret": self._settings.SLACK_CLIENT_SECRET,
            "redirect_uri": self._settings.SLACK_REDIRECT_URI,
        })
        data = r.json()
        if not data.get("ok"):
            raise ValueError(data.get("error", "Slack OAuth failed"))
        return data
```

Replace the `async with` block inside `search_messages` (keep the result-mapping code below it):

```python
    async def search_messages(
        self, access_token: str, query: str, count: int = 20,
    ) -> list[dict]:
        """Search workspace messages mentioning the query (client name)."""
        r = await request_with_retry(
            "GET",
            f"{self.API_BASE}/search.messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"query": query, "count": count, "sort": "timestamp", "sort_dir": "desc"},
            timeout=15,
        )
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
```

Replace the `async with` block inside `get_workspace_info`:

```python
    async def get_workspace_info(self, access_token: str) -> dict:
        """Get workspace name and team info."""
        r = await request_with_retry(
            "GET",
            f"{self.API_BASE}/team.info",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        data = r.json()
        if not data.get("ok"):
            return {}
        team = data.get("team", {})
        return {"name": team.get("name", ""), "domain": team.get("domain", "")}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_connector_clients_retry.py -q`
Expected: PASS — 4 passed (gmail from Task 2 + the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/external/gdrive_client.py app/infrastructure/external/gcal_client.py app/infrastructure/external/slack_client.py tests/unit/test_connector_clients_retry.py
git commit -m "refactor(S6): route Drive/Calendar/Slack clients through the retry wrapper"
```

---

### Task 4: Gmail pagination max-iterations guard

**Files:**
- Modify: `app/infrastructure/external/gmail_client.py`
- Test: `tests/unit/test_gmail_client_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_gmail_client_hardening.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


# Safety bound: if the iteration cap is missing the loop is infinite, so the
# fake raises after 200 calls — the test then FAILS cleanly instead of hanging.
_SAFETY_BOUND = 200


@pytest.mark.asyncio
async def test_fetch_messages_for_domain_bounded_when_pagetoken_never_ends():
    """Google returning 0 results with a perpetually non-null pageToken must
    not loop forever — the iteration cap stops it."""
    client = GmailClient()
    calls = {"n": 0}

    async def fake_search(_self, _access_token, _q, _max_results, _page_token):
        calls["n"] += 1
        if calls["n"] > _SAFETY_BOUND:
            raise AssertionError("pagination did not terminate — no iteration cap")
        return [], "endless-token"

    with patch.object(GmailClient, "search_messages", new=fake_search):
        out = await client.fetch_messages_for_domain("tok", "acme.com", limit=200)

    assert out == []
    assert calls["n"] == 50  # MAX_PAGE_ITERATIONS — bounded, not infinite


@pytest.mark.asyncio
async def test_fetch_recent_messages_bounded_when_pagetoken_never_ends():
    client = GmailClient()
    calls = {"n": 0}

    async def fake_search(_self, _access_token, _q, _max_results, _page_token):
        calls["n"] += 1
        if calls["n"] > _SAFETY_BOUND:
            raise AssertionError("pagination did not terminate — no iteration cap")
        return [], "endless-token"

    with patch.object(GmailClient, "search_messages", new=fake_search):
        out = await client.fetch_recent_messages("tok", lookback_days=30, limit=200)

    assert out == []
    assert calls["n"] == 50
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_gmail_client_hardening.py -q`
Expected: FAIL — both tests fail with `AssertionError: pagination did not terminate — no iteration cap`. The fake's safety bound (200 calls) makes the missing-cap bug fail cleanly instead of hanging the suite.

- [ ] **Step 3: Add the iteration cap**

In `app/infrastructure/external/gmail_client.py`, add a module-level constant after `logger = logging.getLogger(__name__)` (line 12):

```python
logger = logging.getLogger(__name__)

# Hard cap on Gmail search pagination — comfortably above any real
# `limit / batch_size`. Bounds the pathological case where Google returns
# 0 messages but a non-null `nextPageToken`.
MAX_PAGE_ITERATIONS = 50
```

In `fetch_messages_for_domain`, replace the `while` loop header and add the guard as the first statements inside it:

```python
        all_messages = []
        page_token = None
        iterations = 0

        while len(all_messages) < limit:
            iterations += 1
            if iterations > MAX_PAGE_ITERATIONS:
                logger.warning(
                    "gmail pagination hit max iterations; stopping",
                    extra={
                        "event": "connector.gmail.pagination_cap",
                        "domain": domain,
                        "collected": len(all_messages),
                    },
                )
                break
            batch_size = min(100, limit - len(all_messages))
            msg_refs, page_token = await self.search_messages(access_token, query, batch_size, page_token)
```

In `fetch_recent_messages`, apply the same change:

```python
        all_messages: list[dict] = []
        page_token: str | None = None
        iterations = 0

        while len(all_messages) < limit:
            iterations += 1
            if iterations > MAX_PAGE_ITERATIONS:
                logger.warning(
                    "gmail pagination hit max iterations; stopping",
                    extra={
                        "event": "connector.gmail.pagination_cap",
                        "scan": "recent",
                        "collected": len(all_messages),
                    },
                )
                break
            batch_size = min(100, limit - len(all_messages))
            msg_refs, page_token = await self.search_messages(
                access_token, query, batch_size, page_token,
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_gmail_client_hardening.py tests/unit/test_gmail_client_fetch_recent.py -q`
Expected: PASS — the new cap tests pass and the existing fetch tests (which terminate normally on a `None` page token) still pass.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/external/gmail_client.py tests/unit/test_gmail_client_hardening.py
git commit -m "fix(S6): bound gmail pagination loops with a max-iterations cap"
```

---

### Task 5: Gmail bad-date returns None instead of a fabricated timestamp

**Files:**
- Modify: `app/infrastructure/external/gmail_client.py`
- Test: `tests/unit/test_gmail_client_hardening.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_gmail_client_hardening.py`:

```python
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_get_message_returns_none_date_on_unparseable_header():
    """An unparseable Date header must not be disguised as a real
    timestamp — get_message returns date=None and lets the persistence
    layer apply its timezone-aware fallback."""
    client = GmailClient()
    payload = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "",
        "payload": {
            "headers": [
                {"name": "From", "value": "a@acme.com"},
                {"name": "Date", "value": "not-a-real-date"},
            ]
        },
    }

    async def fake_retry(_method, _url, **_kwargs):
        return SimpleNamespace(json=lambda: payload)

    with patch(
        "app.infrastructure.external.gmail_client.request_with_retry", new=fake_retry
    ):
        msg = await client.get_message("tok", "m1")

    assert msg["date"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_gmail_client_hardening.py::test_get_message_returns_none_date_on_unparseable_header -q`
Expected: FAIL — `assert msg["date"] is None` fails because `get_message` currently returns `datetime.now()`.

- [ ] **Step 3: Change the date fallback**

In `app/infrastructure/external/gmail_client.py`, inside `get_message`, replace the date-parsing block:

```python
        date_str = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "gmail message date unparseable; leaving date unset",
                extra={
                    "event": "connector.gmail.bad_date",
                    "raw": date_str[:40],
                    "error": str(exc),
                },
            )
            date = None
```

The return dict's `"date": date` line is unchanged — it now carries `None` on a parse failure. The persistence layer already tolerates this: `connector_viewmodel.py:324` does `msg["date"] if isinstance(msg["date"], datetime) else now`, where `now` is the timezone-aware `datetime.now(timezone.utc)` — so the `NOT NULL EmailIndex.date` column still gets a value, applied consistently at one point.

`datetime` and `datetime.now` are still imported and used elsewhere in the file (`fetch_recent_messages`), so leave the imports unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_gmail_client_hardening.py tests/integration/test_sync_emails_viewmodel.py tests/unit/test_sync_emails_viewmodel.py -q`
Expected: PASS — the new test passes; the sync-email tests confirm the viewmodel still persists rows when `date` is `None`.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/external/gmail_client.py tests/unit/test_gmail_client_hardening.py
git commit -m "fix(S6): gmail get_message returns None for unparseable email dates"
```

---

### Task 6: `_extract_domains` guards against malformed email addresses

**Files:**
- Modify: `app/viewmodels/connector_viewmodel.py`
- Test: `tests/unit/test_extract_domains.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_extract_domains.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from app.viewmodels.connector_viewmodel import ConnectorViewModel


def test_extract_domains_skips_email_without_at_sign():
    """A contact email lacking an '@' must be skipped, not crash or
    produce a bogus domain entry."""
    # _extract_domains does not touch `self`; bypass __init__ to avoid the
    # DB-session dependency.
    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    good = SimpleNamespace(name="Acme", contacts=[{"email": "ceo@acme.com"}])
    malformed = SimpleNamespace(name="Broken", contacts=[{"email": "not-an-email"}])

    result = vm._extract_domains([good, malformed])

    assert result == {"acme.com": "Acme"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_extract_domains.py -q`
Expected: FAIL — `assert {"acme.com": ..., "not-an-email": "Broken"} == {"acme.com": "Acme"}`. Without the guard, `"not-an-email".split("@")[-1]` returns the whole string and it lands in `domain_map`.

- [ ] **Step 3: Add the guard**

In `app/viewmodels/connector_viewmodel.py`, in `_extract_domains` (around line 493), add the `@` check before splitting:

```python
            for contact in contacts:
                if isinstance(contact, dict) and contact.get("email"):
                    email = contact["email"]
                    if "@" not in email:
                        continue
                    domain = email.split("@")[-1].lower()
                    if domain not in FREEMAIL_DOMAINS:
                        domain_map[domain] = client.name
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_extract_domains.py -q`
Expected: PASS — 1 passed

- [ ] **Step 5: Commit**

```bash
git add app/viewmodels/connector_viewmodel.py tests/unit/test_extract_domains.py
git commit -m "fix(S6): guard _extract_domains against emails without an @"
```

---

### Task 7: LLM call timeout on the Bedrock client

**Files:**
- Modify: `app/services/llm.py`
- Test: `tests/unit/test_llm_timeout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_llm_timeout.py`:

```python
from __future__ import annotations


def test_ai_service_passes_timeout_to_bedrock_client(monkeypatch):
    """AIService must construct AsyncAnthropicBedrock with an explicit
    timeout so a hung Bedrock call cannot stall a pipeline phase."""
    captured: dict = {}

    class FakeBedrock:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.services.llm.AsyncAnthropicBedrock", FakeBedrock)

    from app.services.llm import LLM_TIMEOUT_SECONDS, AIService

    AIService()

    assert captured["timeout"] == LLM_TIMEOUT_SECONDS
    assert LLM_TIMEOUT_SECONDS == 120.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_llm_timeout.py -q`
Expected: FAIL — `ImportError: cannot import name 'LLM_TIMEOUT_SECONDS'` (the constant does not exist yet).

- [ ] **Step 3: Add the timeout**

In `app/services/llm.py`, add a module-level constant near the top (after the imports, before `class AIService`):

```python
# Hard ceiling on a single Bedrock call. Pipeline phases run as independent
# ARQ jobs; without this a hung call stalls the whole phase indefinitely.
LLM_TIMEOUT_SECONDS = 120.0
```

In `AIService.__init__`, pass it to the client constructor:

```python
    def __init__(self, aws_region: str | None = None, aws_profile: str | None = None):
        settings = get_settings()
        kwargs: dict[str, Any] = {
            "aws_region": aws_region or settings.AWS_REGION,
            "timeout": LLM_TIMEOUT_SECONDS,
        }
        # Only pass profile if explicitly set — otherwise let the SDK credential
        # chain (env vars, instance role) take over.
        profile = aws_profile if aws_profile is not None else settings.AWS_PROFILE
        if profile:
            kwargs["aws_profile"] = profile
        self.client = AsyncAnthropicBedrock(**kwargs)
        self._models = _tier_models(settings)
        self.default_tier = Tier.BALANCED
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_llm_timeout.py tests/unit/test_anthropic_facade.py -q`
Expected: PASS — the new test passes and the existing facade tests still pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/llm.py tests/unit/test_llm_timeout.py
git commit -m "fix(S6): set an explicit timeout on the Bedrock LLM client"
```

---

### Task 8: Raise client_repo search default cap

**Files:**
- Modify: `app/infrastructure/db/repositories/client_repo.py`
- Test: `tests/unit/test_client_repo_limit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_client_repo_limit.py`:

```python
from __future__ import annotations

import inspect

from app.infrastructure.db.repositories.client_repo import ClientRepository


def test_client_repo_search_default_limit_is_500():
    """Agencies with more than 50 clients must not silently lose the tail
    of their client list."""
    sig = inspect.signature(ClientRepository.search)
    assert sig.parameters["limit"].default == 500
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_client_repo_limit.py -q`
Expected: FAIL — `assert 50 == 500`

- [ ] **Step 3: Raise the cap**

In `app/infrastructure/db/repositories/client_repo.py`, change the `search` signature default:

```python
    async def search(
        self,
        agency_id: UUID | str,
        query: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 500,
    ) -> list[Client]:
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_client_repo_limit.py tests/integration/test_clients_api.py tests/integration/test_repositories.py -q`
Expected: PASS — the new test passes and the existing client tests still pass.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/db/repositories/client_repo.py tests/unit/test_client_repo_limit.py
git commit -m "fix(S6): raise client_repo search default cap from 50 to 500"
```

---

### Task 9: Full regression + documentation update

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`
- Modify: `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md`

- [ ] **Step 1: Run the full backend test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — all backend tests green. Baseline was 339; this plan adds 5 (`test_retry`) + 4 (`test_connector_clients_retry`) + 3 (`test_gmail_client_hardening`) + 1 (`test_extract_domains`) + 1 (`test_llm_timeout`) + 1 (`test_client_repo_limit`) = **15 new tests → expect 354 passed**.

If anything fails, fix it before continuing — do not proceed with a red suite.

- [ ] **Step 2: Verify no connector client still constructs httpx.AsyncClient directly**

Run: `grep -rn "httpx.AsyncClient" app/infrastructure/external/`
Expected: no matches in `gmail_client.py`, `gdrive_client.py`, `gcal_client.py`, `slack_client.py` — every connector HTTP call now goes through `request_with_retry`. (`_retry.py` itself is the one expected match.)

- [ ] **Step 3: Update HANDOFF.md**

In `docs/superpowers/HANDOFF.md`, update the roadmap status line near the top from the S5 wording to:

```
**M16-M20 roadmap status:** S1–S6 COMPLETE. The original plan is fully shipped; the 3 deferred frontend follow-ups are now tracked as S7.
```

Add a short section under "What happened this session" describing S6: the shared `request_with_retry` wrapper, the four hardening fixes, rate limiting dropped, frontend follow-ups split to S7, new test count.

- [ ] **Step 4: Update build-progress memory**

In `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md`, flip the S6 row to COMPLETE and note that S7 (the 3 deferred frontend follow-ups) is the only remaining tracked work.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S6): mark S6 complete; connector resilience shipped"
```

(The memory file lives outside the repo — it is updated in place, not committed.)

---

## Self-review notes

- **Spec coverage:** retry wrapper → Task 1; client migrations → Tasks 2-3; pagination cap → Task 4; bad-date → Task 5; `@` validation → Task 6; LLM timeout → Task 7; `client_repo` cap → Task 8; regression + docs → Task 9. Rate limiting and the frontend follow-ups are spec non-goals — correctly absent.
- **Naming consistency:** `request_with_retry`, `MAX_PAGE_ITERATIONS`, `LLM_TIMEOUT_SECONDS`, `_extract_domains`, `_sleep` are used identically wherever referenced.
- **No schema change:** confirmed — `EmailIndex.date` stays `NOT NULL`; the `None` date is resolved at the existing viewmodel coercion point.
- **Ordering:** Tasks 5 and 2's tests patch `request_with_retry` in `gmail_client`, so Task 2 (which adds that import) must land first — the sequence respects this.
