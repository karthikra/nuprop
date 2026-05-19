# Client Discovery from Gmail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a discovery flow that scans the user's connected Gmail inbox, proposes candidate clients (with auto-filled contacts), and lets the user bulk-select then sequentially review-and-save them — eliminating the chicken-and-egg problem where Gmail sync today requires clients to exist before it can find anything.

**Architecture:** New backend endpoint `POST /api/v1/connectors/gmail/discover-clients` that fetches recent messages without a domain filter, aggregates senders/recipients by domain, filters noise, and returns ranked candidates. New frontend `<ClientDiscoveryFlow>` state machine that walks: lookback picker → scanning → candidate list → sequential review wizard → done. The existing `sync_emails` flow and manual `ClientForm` remain untouched (but the form gains an inline contacts editor as a prerequisite for the review wizard's pre-fill).

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 (backend), React + TypeScript + Tailwind + TanStack Query + vitest (frontend), pytest + httpx mocks (backend tests), MSW (frontend integration tests).

**Spec:** `docs/superpowers/specs/2026-05-19-client-discovery-from-gmail-design.md`

**Run commands:**
- Backend tests: `cd backend && .venv/bin/python -m pytest tests/<path> -v`
- Frontend tests: `cd frontend && pnpm vitest run src/<path>`
- All frontend tests: `cd frontend && pnpm test`
- Full backend suite: `cd backend && .venv/bin/python -m pytest -q`
- Build (frontend): `cd frontend && pnpm build`
- Lint (frontend): `cd frontend && pnpm lint`

---

## File Structure

**Created (backend):**
- `backend/app/domain/schemas/discovery_schemas.py` — `DiscoveryRequest`, `TopSender`, `Candidate`, `DiscoveryResponse`
- `backend/app/services/connectors/discovery_aggregator.py` — pure aggregation logic, `SAAS_NOISE_DOMAINS`, `NO_REPLY_PATTERN`, `suggest_name_from_domain`, `aggregate`
- `backend/tests/unit/test_discovery_aggregator.py`
- `backend/tests/integration/test_discover_clients_endpoint.py`

**Modified (backend):**
- `backend/app/infrastructure/external/gmail_client.py` — add `fetch_recent_messages`
- `backend/app/viewmodels/connector_viewmodel.py` — add `discover_clients` method + import the new schemas
- `backend/app/views/v1/connectors.py` — add `POST /gmail/discover-clients` route

**Created (frontend):**
- `frontend/src/types/discovery.ts` — `Candidate`, `TopSender`, `DiscoveryResponse`
- `frontend/src/api/discovery.ts` — `useDiscoverClients` mutation hook
- `frontend/src/components/clients/discovery/lookback-picker.tsx`
- `frontend/src/components/clients/discovery/candidate-list.tsx`
- `frontend/src/components/clients/discovery/candidate-review-wizard.tsx`
- `frontend/src/components/clients/discovery/client-discovery-flow.tsx`
- `frontend/src/components/clients/discovery/index.ts` — barrel export
- `frontend/src/components/clients/discovery/__tests__/lookback-picker.test.tsx`
- `frontend/src/components/clients/discovery/__tests__/candidate-list.test.tsx`
- `frontend/src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx`
- `frontend/src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx`

**Modified (frontend):**
- `frontend/src/components/clients/client-form.tsx` — accept `initialContacts` prop; add inline contacts editor; include contacts in submit payload
- `frontend/src/components/clients/__tests__/client-form.test.tsx` (extend) — new tests for contacts editor + initialContacts
- `frontend/src/pages/clients/list.tsx` — empty state with two CTAs; populated state with secondary button; mount `<ClientDiscoveryFlow>`
- `frontend/src/pages/clients/__tests__/list.test.tsx` (extend or create) — empty-state CTAs + secondary button visibility

**Untouched (verified during brainstorming):**
- `connector_viewmodel.sync_emails` (the existing Gmail sync flow)
- `_extract_domains`, `FREEMAIL_DOMAINS` (reused by the aggregator)
- Backend DB schema (no migrations — `Client.contacts` already supports the shape we need)

---

## Task 1: Backend schemas

**Files:**
- Create: `backend/app/domain/schemas/discovery_schemas.py`

- [ ] **Step 1: Write the schemas (no test — these are Pydantic dataclasses validated by usage in later tasks)**

Create `backend/app/domain/schemas/discovery_schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    lookback_days: Literal[30, 90, 365]


class TopSender(BaseModel):
    name: str
    email: str
    message_count: int


class Candidate(BaseModel):
    domain: str
    suggested_name: str
    message_count: int
    sender_count: int
    top_senders: list[TopSender]
    first_date: datetime
    last_date: datetime


class DiscoveryResponse(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list)
    excluded_existing: int = 0
    scanned_messages: int = 0
    duration_seconds: float = 0.0
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app.domain.schemas.discovery_schemas import DiscoveryRequest, Candidate, DiscoveryResponse, TopSender; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/domain/schemas/discovery_schemas.py
git commit -m "feat(discovery): pydantic schemas for client discovery from Gmail"
```

---

## Task 2: Discovery aggregator (pure logic)

**Files:**
- Create: `backend/app/services/connectors/discovery_aggregator.py`
- Create: `backend/tests/unit/test_discovery_aggregator.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_discovery_aggregator.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.connectors.discovery_aggregator import (
    SAAS_NOISE_DOMAINS,
    aggregate,
    suggest_name_from_domain,
)


def msg(*, from_: str = "", to: str = "", date: datetime | None = None, msg_id: str = "m"):
    return {
        "id": msg_id,
        "from": from_,
        "to": to,
        "date": date or datetime(2026, 5, 1, tzinfo=timezone.utc),
    }


# ── suggest_name_from_domain ─────────────────────────────────


@pytest.mark.parametrize("domain,expected", [
    ("acme.com", "Acme"),
    ("tatacomms.com", "Tatacomms"),
    ("single.io", "Single"),
    ("mckinsey.com", "Mckinsey"),
])
def test_suggest_name_from_domain(domain: str, expected: str) -> None:
    assert suggest_name_from_domain(domain) == expected


def test_suggest_name_from_subdomain_uses_first_segment() -> None:
    # acknowledged limitation: subdomain → first segment, documented in spec
    assert suggest_name_from_domain("mail.acme.com") == "Mail"


# ── aggregate ────────────────────────────────────────────────


def test_aggregate_empty_messages_returns_empty() -> None:
    assert aggregate([], own_domain=None, excluded_domains=set()) == []


def test_aggregate_single_message_yields_one_candidate() -> None:
    out = aggregate(
        [msg(from_="Jane Doe <jane@acme.com>")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    c = out[0]
    assert c.domain == "acme.com"
    assert c.suggested_name == "Acme"
    assert c.message_count == 1
    assert c.sender_count == 1
    assert c.top_senders[0].email == "jane@acme.com"
    assert c.top_senders[0].name == "Jane Doe"


def test_aggregate_two_senders_same_domain_combine() -> None:
    out = aggregate(
        [
            msg(from_="Jane <jane@acme.com>", msg_id="1"),
            msg(from_="Bob <bob@acme.com>", msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].message_count == 2
    assert out[0].sender_count == 2
    emails = {s.email for s in out[0].top_senders}
    assert emails == {"jane@acme.com", "bob@acme.com"}


def test_aggregate_filters_freemail_sender() -> None:
    out = aggregate(
        [msg(from_="someone@gmail.com")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_saas_noise_sender() -> None:
    out = aggregate(
        [msg(from_=f"notifications@{next(iter(SAAS_NOISE_DOMAINS))}")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_noreply_local_part() -> None:
    out = aggregate(
        [
            msg(from_="noreply@acme.com", msg_id="1"),
            msg(from_="jane@acme.com", msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].message_count == 1
    assert out[0].sender_count == 1
    assert out[0].top_senders[0].email == "jane@acme.com"


def test_aggregate_filters_own_domain() -> None:
    out = aggregate(
        [msg(from_="me@veeville.com")],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_excluded_domain() -> None:
    out = aggregate(
        [msg(from_="jane@acme.com")],
        own_domain=None,
        excluded_domains={"acme.com"},
    )
    assert out == []


def test_aggregate_sort_by_message_count_desc() -> None:
    out = aggregate(
        [
            msg(from_="a@small.com", msg_id="1"),
            msg(from_="a@big.com", msg_id="2"),
            msg(from_="b@big.com", msg_id="3"),
            msg(from_="c@big.com", msg_id="4"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert [c.domain for c in out] == ["big.com", "small.com"]


def test_aggregate_sort_tiebreaker_by_last_date_desc() -> None:
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 5, 1, tzinfo=timezone.utc)
    out = aggregate(
        [
            msg(from_="x@old.com", date=old, msg_id="1"),
            msg(from_="x@new.com", date=new, msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert [c.domain for c in out] == ["new.com", "old.com"]


def test_aggregate_top_senders_capped_at_three_ordered_by_count() -> None:
    msgs = []
    # 4 senders at acme.com with descending counts: a=4, b=3, c=2, d=1
    for i, (name, count) in enumerate([("a", 4), ("b", 3), ("c", 2), ("d", 1)]):
        for j in range(count):
            msgs.append(msg(from_=f"{name}@acme.com", msg_id=f"{name}{j}"))
    out = aggregate(msgs, own_domain=None, excluded_domains=set())
    assert len(out[0].top_senders) == 3
    assert [s.email for s in out[0].top_senders] == [
        "a@acme.com", "b@acme.com", "c@acme.com",
    ]


def test_aggregate_truncates_at_30_candidates() -> None:
    msgs = [msg(from_=f"x@dom{i}.com", msg_id=f"{i}") for i in range(50)]
    out = aggregate(msgs, own_domain=None, excluded_domains=set())
    assert len(out) == 30


def test_aggregate_recipient_direction_counts() -> None:
    # I emailed acme.com → message.to has the address but message.from is mine
    out = aggregate(
        [msg(from_="me@veeville.com", to="Jane <jane@acme.com>")],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].domain == "acme.com"
    assert out[0].message_count == 1


def test_aggregate_mixed_directions_combine() -> None:
    out = aggregate(
        [
            msg(from_="jane@acme.com", to="me@veeville.com", msg_id="1"),
            msg(from_="me@veeville.com", to="bob@acme.com", msg_id="2"),
        ],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].domain == "acme.com"
    assert out[0].message_count == 2
    assert out[0].sender_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_discovery_aggregator.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.services.connectors.discovery_aggregator`.

- [ ] **Step 3: Write the implementation (also moves FREEMAIL_DOMAINS to break the circular import)**

Create `backend/app/services/connectors/discovery_aggregator.py`:

```python
"""
Pure aggregation logic for client discovery from Gmail.

The single source of truth for:
- which domains are considered freemail (FREEMAIL_DOMAINS) and noise (SAAS_NOISE_DOMAINS)
- which sender local-parts are automated (NO_REPLY_PATTERN)
- the company-name guess heuristic (suggest_name_from_domain)
- the per-domain aggregation (aggregate)

Stateless. No I/O. Fully unit-testable.
"""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import getaddresses

from app.domain.schemas.discovery_schemas import Candidate, TopSender

# Personal email providers — sender being on one of these is a strong signal it's
# not a corporate client. Mirrors what was inline in connector_viewmodel.py (which
# now re-imports from here to keep one source of truth).
FREEMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "protonmail.com",
})

# Domains that are almost certainly tooling, not clients. Subjective; grow as patterns emerge.
SAAS_NOISE_DOMAINS: frozenset[str] = frozenset({
    "github.com", "gitlab.com", "bitbucket.org",
    "linear.app", "notion.so", "slack.com",
    "atlassian.com", "jira.com",
    "figma.com", "calendly.com", "zoom.us",
    "mailchimp.com", "sendgrid.net",
    "hubspot.com", "salesforce.com",
    "stripe.com", "paypal.com", "docusign.com",
    "dropbox.com", "box.com",
})

# Local-part prefixes that indicate automated senders. Matches messages but
# preserves the domain's count from human senders at the same domain.
NO_REPLY_PATTERN: re.Pattern[str] = re.compile(
    r"^(noreply|no-reply|notifications?|mailer-daemon|donotreply|do-not-reply|automated)@",
    re.IGNORECASE,
)

MAX_CANDIDATES = 30
MAX_TOP_SENDERS = 3


def suggest_name_from_domain(domain: str) -> str:
    """Strip TLD + subdomains, capitalize the leftmost label.

    'acme.com' → 'Acme', 'tatacomms.com' → 'Tatacomms', 'mail.acme.com' → 'Mail'.
    Intentionally crude — the review wizard exists to fix bad guesses.
    """
    base = domain.split(".", 1)[0]
    if not base:
        return domain
    return base[:1].upper() + base[1:]


def _parse_addresses(field: str) -> list[tuple[str, str]]:
    """Parse a 'From:' or 'To:' header value into [(display_name, address), ...].

    Returns empty list if parsing yields no usable addresses.
    """
    if not field:
        return []
    parsed = getaddresses([field])
    return [(name, addr.lower()) for name, addr in parsed if addr and "@" in addr]


def _should_skip(
    address: str,
    own_domain: str | None,
    excluded_domains: set[str],
) -> tuple[bool, str | None]:
    """Return (skip, domain). If skip=True, domain may be None.

    Logic order matches the spec:
    - skip messages from no-reply addresses entirely
    - extract domain and check against freemail, SaaS noise, own-domain, excluded
    """
    if NO_REPLY_PATTERN.match(address):
        return True, None
    domain = address.split("@")[-1].lower()
    if not domain:
        return True, None
    if domain in FREEMAIL_DOMAINS:
        return True, None
    if domain in SAAS_NOISE_DOMAINS:
        return True, None
    if own_domain and domain == own_domain.lower():
        return True, None
    if domain in excluded_domains:
        return True, None
    return False, domain


def aggregate(
    messages: list[dict],
    own_domain: str | None,
    excluded_domains: set[str],
) -> list[Candidate]:
    """Group messages by sender/recipient domain into candidate clients.

    A "message" must have keys: id, from, to, date.
    Returns up to MAX_CANDIDATES candidates ranked by message_count desc,
    then last_date desc as tiebreaker.
    """
    by_domain: dict[str, dict] = {}

    for message in messages:
        date = message.get("date")
        if not isinstance(date, datetime):
            continue

        # Collect (display_name, address) pairs from both From and To.
        parties: list[tuple[str, str]] = []
        parties.extend(_parse_addresses(message.get("from", "")))
        parties.extend(_parse_addresses(message.get("to", "")))

        # A single message can touch multiple candidate domains (e.g., me → client).
        # Count it once per unique domain to avoid double-counting on multi-party threads.
        domains_in_this_message: set[str] = set()
        for display_name, address in parties:
            skip, domain = _should_skip(address, own_domain, excluded_domains)
            if skip or domain is None:
                continue
            if domain in domains_in_this_message:
                # Another address at the same domain in this message — still record the sender,
                # but don't bump message_count again.
                bucket = by_domain[domain]
                if address not in bucket["senders"]:
                    bucket["senders"][address] = {"name": display_name or address, "count": 0}
                bucket["senders"][address]["count"] += 1
                continue
            domains_in_this_message.add(domain)

            if domain not in by_domain:
                by_domain[domain] = {
                    "message_count": 0,
                    "senders": {},
                    "first_date": date,
                    "last_date": date,
                }
            bucket = by_domain[domain]
            bucket["message_count"] += 1
            if date < bucket["first_date"]:
                bucket["first_date"] = date
            if date > bucket["last_date"]:
                bucket["last_date"] = date
            if address not in bucket["senders"]:
                bucket["senders"][address] = {"name": display_name or address, "count": 0}
            bucket["senders"][address]["count"] += 1

    candidates: list[Candidate] = []
    for domain, bucket in by_domain.items():
        top = sorted(
            bucket["senders"].items(),
            key=lambda kv: (-kv[1]["count"], kv[0]),
        )[:MAX_TOP_SENDERS]
        candidates.append(Candidate(
            domain=domain,
            suggested_name=suggest_name_from_domain(domain),
            message_count=bucket["message_count"],
            sender_count=len(bucket["senders"]),
            top_senders=[
                TopSender(name=v["name"], email=k, message_count=v["count"])
                for k, v in top
            ],
            first_date=bucket["first_date"],
            last_date=bucket["last_date"],
        ))

    candidates.sort(key=lambda c: (-c.message_count, -c.last_date.timestamp()))
    return candidates[:MAX_CANDIDATES]
```

- [ ] **Step 4: Update connector_viewmodel to import FREEMAIL_DOMAINS from the new location**

Edit `backend/app/viewmodels/connector_viewmodel.py`:

1. Find line ~26 where `FREEMAIL_DOMAINS = {"gmail.com", ...}` is defined and DELETE the assignment.
2. Add this import at the top with the other infrastructure imports:

```python
from app.services.connectors.discovery_aggregator import FREEMAIL_DOMAINS
```

This breaks the circular dependency cleanly — the aggregator no longer reaches into the viewmodel, and the existing `_extract_domains` method (which uses `FREEMAIL_DOMAINS`) keeps working unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_discovery_aggregator.py -v`
Expected: PASS — 14 tests.

Also run the existing sync_emails tests to ensure the FREEMAIL_DOMAINS move didn't break anything:

Run: `cd backend && .venv/bin/python -m pytest tests/ -k "sync_emails or extract_domains" -v`
Expected: all pre-existing pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/connectors/discovery_aggregator.py \
        backend/tests/unit/test_discovery_aggregator.py \
        backend/app/viewmodels/connector_viewmodel.py
git commit -m "feat(discovery): pure aggregator + relocate FREEMAIL_DOMAINS to break circular import"
```

---

## Task 3: GmailClient.fetch_recent_messages

**Files:**
- Modify: `backend/app/infrastructure/external/gmail_client.py` (append a new method at end)
- Add test: `backend/tests/unit/test_gmail_client_fetch_recent.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_gmail_client_fetch_recent.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


@pytest.mark.asyncio
async def test_fetch_recent_messages_builds_after_query_and_paginates() -> None:
    client = GmailClient()
    # First page returns 2 refs + a page token; second page returns 1 ref + no token.
    pages = [
        ([{"id": "a"}, {"id": "b"}], "tok1"),
        ([{"id": "c"}], None),
    ]
    captured_queries: list[str] = []

    async def fake_search(_self, _access_token, q, max_results, page_token):
        captured_queries.append(q)
        return pages.pop(0)

    async def fake_get(_self, _access_token, msg_id):
        return {
            "id": msg_id,
            "thread_id": f"t-{msg_id}",
            "from": f"x@example.com",
            "to": "",
            "subject": "hi",
            "snippet": "",
            "date": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "has_attachments": False,
        }

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=500)

    assert {m["id"] for m in out} == {"a", "b", "c"}
    # All queries should be the same `after:<YYYY/MM/DD>` form
    assert all(q.startswith("after:") for q in captured_queries)


@pytest.mark.asyncio
async def test_fetch_recent_messages_respects_limit() -> None:
    client = GmailClient()
    # Pretend search keeps returning 100 refs per page; cap at limit=150.
    call_count = {"n": 0}

    async def fake_search(_self, _access_token, q, max_results, page_token):
        call_count["n"] += 1
        return ([{"id": f"id-{i}-{call_count['n']}"} for i in range(max_results)], "tok")

    async def fake_get(_self, _access_token, msg_id):
        return {"id": msg_id, "thread_id": "", "from": "", "to": "",
                "subject": "", "snippet": "", "date": datetime.now(timezone.utc),
                "has_attachments": False}

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=150)

    assert len(out) == 150


@pytest.mark.asyncio
async def test_fetch_recent_messages_skips_bad_get_calls() -> None:
    client = GmailClient()

    async def fake_search(_self, _access_token, q, max_results, page_token):
        return ([{"id": "good"}, {"id": "bad"}, {"id": "good2"}], None)

    async def fake_get(_self, _access_token, msg_id):
        if msg_id == "bad":
            raise ValueError("boom")
        return {"id": msg_id, "thread_id": "", "from": "", "to": "",
                "subject": "", "snippet": "", "date": datetime.now(timezone.utc),
                "has_attachments": False}

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=10)

    assert {m["id"] for m in out} == {"good", "good2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_gmail_client_fetch_recent.py -v`
Expected: FAIL with `AttributeError: 'GmailClient' object has no attribute 'fetch_recent_messages'`.

- [ ] **Step 3: Add the new method**

Append the following method to `backend/app/infrastructure/external/gmail_client.py` (after `fetch_messages_for_domain` — line ~187). Add the necessary `timedelta` import at the top if it's not already there:

```python
    async def fetch_recent_messages(
        self,
        access_token: str,
        lookback_days: int,
        limit: int,
    ) -> list[dict]:
        """Fetch up to `limit` recent messages from the last `lookback_days`.

        No domain filter — caller filters/aggregates downstream. Uses the same
        log-and-skip pattern as fetch_messages_for_domain for individual
        get_message failures.
        """
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=lookback_days)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_gmail_client_fetch_recent.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/external/gmail_client.py \
        backend/tests/unit/test_gmail_client_fetch_recent.py
git commit -m "feat(discovery): GmailClient.fetch_recent_messages with paging + log-and-skip"
```

---

## Task 4: ConnectorViewModel.discover_clients

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py` — add the method
- Add test: `backend/tests/unit/test_discover_clients_viewmodel.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_discover_clients_viewmodel.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.viewmodels.connector_viewmodel import ConnectorViewModel


@pytest.fixture
def agency_with_gmail():
    return SimpleNamespace(
        id=uuid4(),
        settings={"gmail": {"connected": True, "refresh_token": "enc-token",
                            "email": "owner@veeville.com"}},
    )


@pytest.mark.asyncio
async def test_discover_clients_returns_candidates_filtered_by_existing(
    agency_with_gmail,
) -> None:
    vm = ConnectorViewModel.__new__(ConnectorViewModel)  # bypass __init__
    vm.error = None
    vm.status_code = 200

    # Stub dependencies
    vm.agency_repo = MagicMock()
    vm.agency_repo.get_by_id = AsyncMock(return_value=agency_with_gmail)
    vm.client_repo = MagicMock()
    # one existing client with a contact at tatacomms.com
    existing_client = SimpleNamespace(
        name="Tata", contacts=[{"name": "X", "email": "x@tatacomms.com"}],
    )
    vm.client_repo.search = AsyncMock(return_value=[existing_client])

    vm._gmail = MagicMock()
    vm._gmail.refresh_access_token = AsyncMock(return_value="access")
    vm._gmail.fetch_recent_messages = AsyncMock(return_value=[
        {"id": "1", "from": "Jane <jane@acme.com>", "to": "",
         "date": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        {"id": "2", "from": "Bob <bob@tatacomms.com>", "to": "",
         "date": datetime(2026, 5, 1, tzinfo=timezone.utc)},
    ])

    vm._decrypt = MagicMock(return_value="raw-token")

    resp = await vm.discover_clients(agency_with_gmail.id, lookback_days=90)

    domains = {c.domain for c in resp.candidates}
    assert domains == {"acme.com"}  # tatacomms.com filtered out as already-linked
    assert resp.excluded_existing == 1
    assert resp.scanned_messages == 2


@pytest.mark.asyncio
async def test_discover_clients_errors_when_gmail_not_connected() -> None:
    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200

    agency = SimpleNamespace(id=uuid4(), settings={"gmail": {"connected": False}})
    vm.agency_repo = MagicMock()
    vm.agency_repo.get_by_id = AsyncMock(return_value=agency)

    resp = await vm.discover_clients(agency.id, lookback_days=90)
    assert resp.candidates == []
    assert vm.error == "Gmail not connected"
    assert vm.status_code == 400


@pytest.mark.asyncio
async def test_discover_clients_handles_decrypt_failure() -> None:
    from app.core.errors import TokenVaultError

    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200

    agency = SimpleNamespace(
        id=uuid4(),
        settings={"gmail": {"connected": True, "refresh_token": "bad", "email": "x@y.com"}},
    )
    vm.agency_repo = MagicMock()
    vm.agency_repo.get_by_id = AsyncMock(return_value=agency)
    vm._decrypt = MagicMock(side_effect=TokenVaultError(code="decrypt_failed", message="x"))

    resp = await vm.discover_clients(agency.id, lookback_days=90)
    assert resp.candidates == []
    assert vm.status_code == 401
    assert "decrypt" in vm.error.lower() or "reconnect" in vm.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_discover_clients_viewmodel.py -v`
Expected: FAIL with `AttributeError: 'ConnectorViewModel' object has no attribute 'discover_clients'`.

- [ ] **Step 3: Add the method**

Append the following to `backend/app/viewmodels/connector_viewmodel.py`. Locate a sensible spot — just after the existing `sync_emails` method (around line 370, before `_extract_domains`). Also add imports at the top if missing:

```python
import time
from app.domain.schemas.discovery_schemas import DiscoveryResponse
from app.services.connectors.discovery_aggregator import aggregate
```

Method body:

```python
    async def discover_clients(
        self, agency_id: UUID, lookback_days: int,
    ) -> DiscoveryResponse:
        start = time.time()

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return DiscoveryResponse()

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            self.error = "Gmail not connected"
            self.status_code = 400
            return DiscoveryResponse()

        try:
            refresh_token = self._decrypt(gmail["refresh_token"])
        except TokenVaultError:
            self.error = "Stored Gmail credentials could not be decrypted; please reconnect"
            self.status_code = 401
            return DiscoveryResponse()

        try:
            access_token = await self._gmail.refresh_access_token(refresh_token)
        except Exception:
            logger.exception(
                "gmail.refresh_access_token failed during discovery",
                extra={"event": "connector.discovery.refresh_failed"},
            )
            self.error = "Failed to refresh Google access token; please reconnect"
            self.status_code = 401
            return DiscoveryResponse()

        # Per-window limits chosen to bound Gmail API calls. See spec.
        limit_for_window = {30: 500, 90: 1500, 365: 3000}[lookback_days]

        try:
            messages = await self._gmail.fetch_recent_messages(
                access_token, lookback_days=lookback_days, limit=limit_for_window,
            )
        except Exception:
            logger.exception(
                "gmail.fetch_recent_messages failed",
                extra={"event": "connector.discovery.fetch_failed"},
            )
            self.error = "Couldn't scan your inbox right now. Try again in a minute."
            self.status_code = 500
            return DiscoveryResponse()

        # Build the already-linked domain set from existing clients.
        clients = await self.client_repo.search(agency_id, limit=500)
        linked_domains: set[str] = set()
        for client in clients:
            for contact in (client.contacts or []):
                if isinstance(contact, dict) and contact.get("email"):
                    linked_domains.add(contact["email"].split("@")[-1].lower())

        # Own domain inferred from the connected Gmail account.
        own_email = (gmail.get("email") or "").strip()
        own_domain = own_email.split("@")[-1].lower() if "@" in own_email else None

        candidates = aggregate(
            messages,
            own_domain=own_domain,
            excluded_domains=linked_domains,
        )

        return DiscoveryResponse(
            candidates=candidates,
            excluded_existing=len(linked_domains),
            scanned_messages=len(messages),
            duration_seconds=round(time.time() - start, 2),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_discover_clients_viewmodel.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py \
        backend/tests/unit/test_discover_clients_viewmodel.py
git commit -m "feat(discovery): ConnectorViewModel.discover_clients orchestrator"
```

---

## Task 5: Discovery route

**Files:**
- Modify: `backend/app/views/v1/connectors.py` — add new route
- Add test: `backend/tests/integration/test_discover_clients_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_discover_clients_endpoint.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_discover_endpoint_returns_candidates(
    test_client, registered_agency_with_gmail,
) -> None:
    """End-to-end: POST /api/v1/connectors/gmail/discover-clients with stubbed Gmail.

    `registered_agency_with_gmail` (conftest fixture) creates an authenticated
    session whose agency has settings.gmail.connected=True and a fake
    refresh_token already stored encrypted.
    """
    fake_messages = [
        {"id": "1", "from": "Jane <jane@acme.com>", "to": "",
         "date": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        {"id": "2", "from": "Bob <bob@acme.com>", "to": "",
         "date": datetime(2026, 5, 2, tzinfo=timezone.utc)},
    ]

    with (
        patch(
            "app.infrastructure.external.gmail_client.GmailClient.refresh_access_token",
            new=AsyncMock(return_value="access-tok"),
        ),
        patch(
            "app.infrastructure.external.gmail_client.GmailClient.fetch_recent_messages",
            new=AsyncMock(return_value=fake_messages),
        ),
    ):
        r = await test_client.post(
            "/api/v1/connectors/gmail/discover-clients",
            json={"lookback_days": 90},
        )

    assert r.status_code == 200
    body = r.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["domain"] == "acme.com"
    assert body["candidates"][0]["suggested_name"] == "Acme"
    assert body["scanned_messages"] == 2


@pytest.mark.asyncio
async def test_discover_endpoint_400_on_invalid_lookback(
    test_client, registered_agency_with_gmail,
) -> None:
    r = await test_client.post(
        "/api/v1/connectors/gmail/discover-clients",
        json={"lookback_days": 7},  # not in {30, 90, 365}
    )
    assert r.status_code == 422  # pydantic Literal rejects it
```

> **Note for implementer:** If `registered_agency_with_gmail` doesn't yet exist as a fixture in `tests/integration/conftest.py`, create it modeled after the existing `registered_agency` fixture (you'll find it in the same conftest). It must set `agency.settings = {"gmail": {"connected": True, "refresh_token": <Fernet-encrypted "fake-token">, "email": "owner@veeville.com"}}` and commit. If a Fernet helper exists in the conftest already, reuse it; otherwise inline a `Fernet(os.environ["ENCRYPTION_KEY"]).encrypt(...)` call.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_discover_clients_endpoint.py -v`
Expected: FAIL — either `404` (route not registered) or fixture not found.

- [ ] **Step 3: Add the route**

Open `backend/app/views/v1/connectors.py`. After the existing `gmail_sync` route (around line 84), add:

```python
from app.domain.schemas.discovery_schemas import DiscoveryRequest, DiscoveryResponse


@router.post("/gmail/discover-clients", response_model=DiscoveryResponse)
async def gmail_discover_clients(
    body: DiscoveryRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.discover_clients(agency_id, lookback_days=body.lookback_days)
    if vm.error:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_discover_clients_endpoint.py -v`
Expected: PASS — 2 tests.

Run full backend suite to check nothing else broke:

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 244 + new tests passing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/views/v1/connectors.py \
        backend/tests/integration/test_discover_clients_endpoint.py
# also include conftest changes if you added the new fixture
git commit -m "feat(discovery): POST /connectors/gmail/discover-clients route"
```

---

## Task 6: Frontend types + API hook

**Files:**
- Create: `frontend/src/types/discovery.ts`
- Create: `frontend/src/api/discovery.ts`

- [ ] **Step 1: Write the types**

Create `frontend/src/types/discovery.ts`:

```typescript
export interface TopSender {
  name: string
  email: string
  message_count: number
}

export interface Candidate {
  domain: string
  suggested_name: string
  message_count: number
  sender_count: number
  top_senders: TopSender[]
  first_date: string
  last_date: string
}

export interface DiscoveryResponse {
  candidates: Candidate[]
  excluded_existing: number
  scanned_messages: number
  duration_seconds: number
}

export type LookbackDays = 30 | 90 | 365
```

- [ ] **Step 2: Write the hook**

Create `frontend/src/api/discovery.ts`:

```typescript
import { useMutation } from '@tanstack/react-query'
import { api } from './client'
import type { DiscoveryResponse, LookbackDays } from '../types/discovery'

export function useDiscoverClients() {
  return useMutation({
    mutationFn: async (lookback_days: LookbackDays) => {
      const res = await api.post<DiscoveryResponse>(
        '/connectors/gmail/discover-clients',
        { lookback_days },
      )
      return res.data
    },
  })
}
```

- [ ] **Step 3: Verify it builds**

Run from frontend: `pnpm tsc --noEmit`
Expected: no errors related to the new files.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/discovery.ts frontend/src/api/discovery.ts
git commit -m "feat(discovery): types + useDiscoverClients hook"
```

---

## Task 7: Extend ClientForm with contacts editor

**Files:**
- Modify: `frontend/src/components/clients/client-form.tsx`
- Extend (or create): `frontend/src/components/clients/__tests__/client-form.test.tsx`

**⚠️ Pattern reminder (from rate-card-wizard):** Tests on controlled inputs MUST use a stateful `Wrapper` with `useState`. Don't use `defaultValue` / `key={value}` to work around test-harness issues.

- [ ] **Step 1: Write the failing tests**

Create or extend `frontend/src/components/clients/__tests__/client-form.test.tsx` with these tests (if file exists, add inside the existing `describe`):

```typescript
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClientForm } from '../client-form'
import type { ClientCreate, ContactInfo } from '../../../types/client'

function Wrapper({
  initialContacts,
  onSubmit,
}: {
  initialContacts?: ContactInfo[]
  onSubmit?: (data: ClientCreate) => void
}) {
  return (
    <ClientForm
      onSubmit={onSubmit ?? (() => {})}
      onCancel={() => {}}
      saving={false}
      initialContacts={initialContacts}
    />
  )
}

describe('ClientForm contacts editor', () => {
  it('pre-fills contacts from initialContacts', () => {
    render(<Wrapper initialContacts={[
      { name: 'Jane', email: 'jane@acme.com' },
      { name: 'Bob', email: 'bob@acme.com' },
    ]} />)
    expect(screen.getByDisplayValue('Jane')).toBeInTheDocument()
    expect(screen.getByDisplayValue('jane@acme.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Bob')).toBeInTheDocument()
  })

  it('includes contacts in the submit payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper
      initialContacts={[{ name: 'Jane', email: 'jane@acme.com' }]}
      onSubmit={onSubmit}
    />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Acme',
      contacts: [{ name: 'Jane', email: 'jane@acme.com' }],
    }))
  })

  it('lets the user add a new contact row', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    await user.click(screen.getByRole('button', { name: /add contact/i }))
    const nameInputs = screen.getAllByPlaceholderText(/contact name/i)
    const emailInputs = screen.getAllByPlaceholderText(/contact email/i)
    await user.type(nameInputs[0], 'Carol')
    await user.type(emailInputs[0], 'carol@acme.com')
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      contacts: [{ name: 'Carol', email: 'carol@acme.com' }],
    }))
  })

  it('lets the user remove a contact row', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper
      initialContacts={[
        { name: 'Jane', email: 'jane@acme.com' },
        { name: 'Bob', email: 'bob@acme.com' },
      ]}
      onSubmit={onSubmit}
    />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    // Remove "Bob" row
    const removeButtons = screen.getAllByRole('button', { name: /remove contact/i })
    await user.click(removeButtons[1])
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      contacts: [{ name: 'Jane', email: 'jane@acme.com' }],
    }))
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm vitest run src/components/clients/__tests__/client-form.test.tsx`
Expected: FAIL — `initialContacts` prop doesn't exist; contacts editor missing.

- [ ] **Step 3: Modify the ClientForm**

Replace the entire contents of `frontend/src/components/clients/client-form.tsx` with:

```typescript
import { useState } from 'react'
import type { Client, ClientCreate, ContactInfo } from '../../types/client'

interface Props {
  initial?: Client
  initialContacts?: ContactInfo[]
  onSubmit: (data: ClientCreate) => void
  onCancel: () => void
  saving: boolean
}

const SIZE_OPTIONS = ['startup', 'sme', 'enterprise']

export function ClientForm({ initial, initialContacts, onSubmit, onCancel, saving }: Props) {
  const [name, setName] = useState(initial?.name || '')
  const [industry, setIndustry] = useState(initial?.industry || '')
  const [size, setSize] = useState(initial?.size || '')
  const [notes, setNotes] = useState(initial?.notes || '')
  const [tags, setTags] = useState(initial?.tags?.join(', ') || '')
  const [contacts, setContacts] = useState<ContactInfo[]>(
    initialContacts ?? initial?.contacts ?? [],
  )

  const updateContact = (idx: number, field: 'name' | 'email', value: string) => {
    setContacts((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)))
  }
  const addContact = () => setContacts((prev) => [...prev, { name: '', email: '' }])
  const removeContact = (idx: number) =>
    setContacts((prev) => prev.filter((_, i) => i !== idx))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanContacts = contacts
      .map((c) => ({ name: c.name.trim(), email: (c.email || '').trim() }))
      .filter((c) => c.name || c.email)
    onSubmit({
      name,
      industry: industry || undefined,
      size: size || undefined,
      notes: notes || undefined,
      tags: tags ? tags.split(',').map((t) => t.trim()).filter(Boolean) : [],
      contacts: cleanContacts.length ? cleanContacts : undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="client-name" className="block text-sm font-medium text-stone-700">Client name *</label>
        <input
          id="client-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-stone-700">Industry</label>
          <input
            type="text"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g. Telecom, Retail"
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700">Size</label>
          <select
            value={size}
            onChange={(e) => setSize(e.target.value)}
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          >
            <option value="">—</option>
            {SIZE_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Contacts editor */}
      <div>
        <label className="block text-sm font-medium text-stone-700 mb-2">Contacts</label>
        <div className="space-y-2">
          {contacts.map((c, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Contact name"
                value={c.name}
                onChange={(e) => updateContact(idx, 'name', e.target.value)}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <input
                type="email"
                placeholder="Contact email"
                value={c.email || ''}
                onChange={(e) => updateContact(idx, 'email', e.target.value)}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <button
                type="button"
                onClick={() => removeContact(idx)}
                aria-label="Remove contact"
                className="text-stone-300 hover:text-red-500 text-sm px-1"
              >✕</button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={addContact}
          className="mt-2 text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900"
        >
          + Add contact
        </button>
      </div>

      <div>
        <label className="block text-sm font-medium text-stone-700">Tags</label>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="comma, separated, tags"
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-stone-700">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving || !name.trim()}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {saving ? 'Saving…' : initial ? 'Save' : 'Create client'}
        </button>
      </div>
    </form>
  )
}
```

> **Note for implementer:** The existing form's exact JSX may differ slightly from the above (the Read I did earlier showed only the first 50 lines). The intent is: keep all existing fields (name, industry, size, notes, tags); ADD the contacts editor and the `initialContacts` prop; INCLUDE contacts in the submit payload. If the existing layout differs in styling, preserve it — only add new prop + new section + new payload field.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm vitest run src/components/clients/__tests__/client-form.test.tsx`
Expected: PASS — 4 new tests (plus any pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/client-form.tsx \
        frontend/src/components/clients/__tests__/client-form.test.tsx
git commit -m "feat(clients): inline contacts editor + initialContacts prop on ClientForm"
```

---

## Task 8: LookbackPicker component

**Files:**
- Create: `frontend/src/components/clients/discovery/lookback-picker.tsx`
- Create: `frontend/src/components/clients/discovery/__tests__/lookback-picker.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/discovery/__tests__/lookback-picker.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LookbackPicker } from '../lookback-picker'

describe('LookbackPicker', () => {
  it('renders three buttons (30, 90, 365 days)', () => {
    render(<LookbackPicker onPick={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByRole('button', { name: /30 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /90 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /365 days/i })).toBeInTheDocument()
  })

  it('calls onPick with the chosen number when a button is clicked', async () => {
    const user = userEvent.setup()
    const onPick = vi.fn()
    render(<LookbackPicker onPick={onPick} onCancel={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))
    expect(onPick).toHaveBeenCalledWith(90)
  })

  it('calls onCancel when the cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<LookbackPicker onPick={vi.fn()} onCancel={onCancel} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/lookback-picker.test.tsx`
Expected: FAIL — module-not-found.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/clients/discovery/lookback-picker.tsx`:

```typescript
import type { LookbackDays } from '../../../types/discovery'

interface Props {
  onPick: (days: LookbackDays) => void
  onCancel: () => void
}

const OPTIONS: { label: string; value: LookbackDays }[] = [
  { label: '30 days',  value: 30 },
  { label: '90 days',  value: 90 },
  { label: '365 days', value: 365 },
]

export function LookbackPicker({ onPick, onCancel }: Props) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-stone-900">Look back how far?</h2>
        <p className="mt-1 text-sm text-stone-500">
          We'll scan your Gmail inbox and suggest candidate clients based on who you've been emailing.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onPick(opt.value)}
            className={`rounded-lg border px-4 py-3 text-sm font-medium transition-colors ${
              opt.value === 90
                ? 'border-stone-900 bg-stone-900 text-white hover:bg-stone-800'
                : 'border-stone-300 bg-white text-stone-700 hover:bg-stone-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="flex justify-end">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/lookback-picker.test.tsx`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/discovery/lookback-picker.tsx \
        frontend/src/components/clients/discovery/__tests__/lookback-picker.test.tsx
git commit -m "feat(discovery): LookbackPicker with 30/90/365 buttons"
```

---

## Task 9: CandidateList component

**Files:**
- Create: `frontend/src/components/clients/discovery/candidate-list.tsx`
- Create: `frontend/src/components/clients/discovery/__tests__/candidate-list.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/discovery/__tests__/candidate-list.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CandidateList } from '../candidate-list'
import type { Candidate, DiscoveryResponse } from '../../../types/discovery'

const C: Candidate = {
  domain: 'acme.com',
  suggested_name: 'Acme',
  message_count: 47,
  sender_count: 3,
  top_senders: [{ name: 'Jane Doe', email: 'jane@acme.com', message_count: 28 }],
  first_date: '2026-04-01T00:00:00Z',
  last_date: '2026-05-18T00:00:00Z',
}

const D: Candidate = { ...C, domain: 'tatacomms.com', suggested_name: 'Tatacomms', message_count: 32 }

const RESPONSE: DiscoveryResponse = {
  candidates: [C, D],
  excluded_existing: 0,
  scanned_messages: 250,
  duration_seconds: 4.2,
}

describe('CandidateList', () => {
  it('renders one row per candidate with name and counts', () => {
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('Tatacomms')).toBeInTheDocument()
    expect(screen.getByText(/47 emails/)).toBeInTheDocument()
    expect(screen.getByText(/3 senders/)).toBeInTheDocument()
  })

  it('disables the Review button when nothing is selected', () => {
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    expect(screen.getByRole('button', { name: /review/i })).toBeDisabled()
  })

  it('enables the Review button after a candidate is checked', async () => {
    const user = userEvent.setup()
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    // Each row has a checkbox role
    const checks = screen.getAllByRole('checkbox')
    await user.click(checks[0])
    expect(screen.getByRole('button', { name: /review 1 selected/i })).toBeEnabled()
  })

  it('calls onReview with the selected candidates', async () => {
    const user = userEvent.setup()
    const onReview = vi.fn()
    render(<CandidateList response={RESPONSE} onReview={onReview} onSkipAll={vi.fn()} />)
    const checks = screen.getAllByRole('checkbox')
    await user.click(checks[0])
    await user.click(checks[1])
    await user.click(screen.getByRole('button', { name: /review 2 selected/i }))
    expect(onReview).toHaveBeenCalledWith([C, D])
  })

  it('renders the excluded_existing note when > 0', () => {
    render(<CandidateList
      response={{ ...RESPONSE, excluded_existing: 3 }}
      onReview={vi.fn()}
      onSkipAll={vi.fn()}
    />)
    expect(screen.getByText(/3 domains already linked/i)).toBeInTheDocument()
  })

  it('renders the no-candidates message when candidates is empty', () => {
    render(<CandidateList
      response={{ candidates: [], excluded_existing: 0, scanned_messages: 47, duration_seconds: 1.2 }}
      onReview={vi.fn()}
      onSkipAll={vi.fn()}
    />)
    expect(screen.getByText(/no client-looking domains/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/candidate-list.test.tsx`
Expected: FAIL — module-not-found.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/clients/discovery/candidate-list.tsx`:

```typescript
import { useState } from 'react'
import type { Candidate, DiscoveryResponse } from '../../../types/discovery'

interface Props {
  response: DiscoveryResponse
  onReview: (selected: Candidate[]) => void
  onSkipAll: () => void
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: 'short', year: 'numeric' })
}

export function CandidateList({ response, onReview, onSkipAll }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (domain: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(domain)) next.delete(domain)
      else next.add(domain)
      return next
    })

  const chosen = response.candidates.filter((c) => selected.has(c.domain))

  if (response.candidates.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-stone-600">
          We scanned {response.scanned_messages} messages but didn't find any client-looking domains
          {response.excluded_existing > 0
            ? ` (${response.excluded_existing} domains already linked to existing clients were excluded)`
            : ''}
          . Try a wider lookback, or add a client manually.
        </p>
        <div className="flex justify-end">
          <button onClick={onSkipAll} className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900">
            Close
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-stone-900">
          Found {response.candidates.length} candidate {response.candidates.length === 1 ? 'client' : 'clients'}
        </h2>
        {response.excluded_existing > 0 && (
          <p className="mt-1 text-xs text-stone-500">
            {response.excluded_existing} domains already linked to existing clients are excluded.
          </p>
        )}
      </div>

      <div className="max-h-96 overflow-y-auto space-y-1.5 border border-stone-200 rounded-lg p-1.5">
        {response.candidates.map((c) => {
          const isOn = selected.has(c.domain)
          return (
            <label
              key={c.domain}
              className={`flex items-start gap-3 p-2.5 rounded-md cursor-pointer ${
                isOn ? 'bg-stone-100' : 'hover:bg-stone-50'
              }`}
            >
              <input
                type="checkbox"
                aria-label={`Select ${c.suggested_name}`}
                checked={isOn}
                onChange={() => toggle(c.domain)}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-stone-900">{c.suggested_name}</span>
                  <span className="font-mono text-xs text-stone-400">{c.domain}</span>
                </div>
                <p className="text-xs text-stone-500 mt-0.5">
                  {c.message_count} emails · {c.sender_count} {c.sender_count === 1 ? 'sender' : 'senders'} ·{' '}
                  {formatDate(c.first_date)}–{formatDate(c.last_date)}
                </p>
              </div>
            </label>
          )
        })}
      </div>

      <div className="flex justify-between items-center pt-1">
        <button onClick={onSkipAll} className="text-sm text-stone-600 hover:text-stone-900">
          Skip all
        </button>
        <button
          onClick={() => onReview(chosen)}
          disabled={chosen.length === 0}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50 disabled:pointer-events-none"
        >
          Review {chosen.length} selected →
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/candidate-list.test.tsx`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/discovery/candidate-list.tsx \
        frontend/src/components/clients/discovery/__tests__/candidate-list.test.tsx
git commit -m "feat(discovery): CandidateList with bulk-select checkboxes"
```

---

## Task 10: CandidateReviewWizard component

**Files:**
- Create: `frontend/src/components/clients/discovery/candidate-review-wizard.tsx`
- Create: `frontend/src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CandidateReviewWizard } from '../candidate-review-wizard'
import type { Candidate } from '../../../types/discovery'
import type { ClientCreate } from '../../../types/client'

const A: Candidate = {
  domain: 'acme.com', suggested_name: 'Acme',
  message_count: 47, sender_count: 2,
  top_senders: [
    { name: 'Jane', email: 'jane@acme.com', message_count: 28 },
    { name: 'Bob',  email: 'bob@acme.com',  message_count: 19 },
  ],
  first_date: '2026-04-01T00:00:00Z', last_date: '2026-05-18T00:00:00Z',
}
const B: Candidate = { ...A, domain: 'tatacomms.com', suggested_name: 'Tatacomms' }

describe('CandidateReviewWizard', () => {
  it('renders the first candidate with name pre-filled and contacts populated', () => {
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={vi.fn()}
      onComplete={vi.fn()}
    />)
    expect(screen.getByText(/reviewing 1 of 2/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Acme')).toBeInTheDocument()
    expect(screen.getByDisplayValue('jane@acme.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('bob@acme.com')).toBeInTheDocument()
  })

  it('Skip advances to next candidate without saving', async () => {
    const user = userEvent.setup()
    const onSaveClient = vi.fn()
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={onSaveClient}
      onComplete={vi.fn()}
    />)
    await user.click(screen.getByRole('button', { name: /skip this/i }))
    expect(onSaveClient).not.toHaveBeenCalled()
    expect(screen.getByText(/reviewing 2 of 2/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Tatacomms')).toBeInTheDocument()
  })

  it('Save & Next saves then advances', async () => {
    const user = userEvent.setup()
    const onSaveClient = vi.fn().mockResolvedValue(undefined)
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={onSaveClient}
      onComplete={vi.fn()}
    />)
    await user.click(screen.getByRole('button', { name: /save & next/i }))
    expect(onSaveClient).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Acme',
      contacts: [
        { name: 'Jane', email: 'jane@acme.com' },
        { name: 'Bob',  email: 'bob@acme.com'  },
      ],
    }))
    expect(await screen.findByText(/reviewing 2 of 2/i)).toBeInTheDocument()
  })

  it('on final candidate, primary button reads "Save & Finish"', () => {
    render(<CandidateReviewWizard
      candidates={[A]}
      onSaveClient={vi.fn()}
      onComplete={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: /save & finish/i })).toBeInTheDocument()
  })

  it('after final save, onComplete fires with created count', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<CandidateReviewWizard
      candidates={[A]}
      onSaveClient={vi.fn().mockResolvedValue(undefined)}
      onComplete={onComplete}
    />)
    await user.click(screen.getByRole('button', { name: /save & finish/i }))
    expect(onComplete).toHaveBeenCalledWith({ created: 1 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx`
Expected: FAIL — module-not-found.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/clients/discovery/candidate-review-wizard.tsx`:

```typescript
import { useState } from 'react'
import { ClientForm } from '../client-form'
import type { Candidate } from '../../../types/discovery'
import type { ClientCreate, ContactInfo } from '../../../types/client'

interface Props {
  candidates: Candidate[]
  onSaveClient: (data: ClientCreate) => Promise<void>
  onComplete: (summary: { created: number }) => void
}

function contactsFromCandidate(c: Candidate): ContactInfo[] {
  return c.top_senders.map((s) => ({ name: s.name, email: s.email }))
}

export function CandidateReviewWizard({ candidates, onSaveClient, onComplete }: Props) {
  const [index, setIndex] = useState(0)
  const [created, setCreated] = useState(0)
  const [saving, setSaving] = useState(false)

  if (candidates.length === 0) {
    // Guard: this shouldn't normally happen — CandidateList prevents zero-select.
    onComplete({ created: 0 })
    return null
  }

  const isLast = index === candidates.length - 1
  const current = candidates[index]

  const advance = (didCreate: boolean) => {
    const newCreated = created + (didCreate ? 1 : 0)
    if (isLast) {
      onComplete({ created: newCreated })
      return
    }
    setCreated(newCreated)
    setIndex((i) => i + 1)
  }

  const handleSubmit = async (data: ClientCreate) => {
    if (saving) return
    setSaving(true)
    try {
      await onSaveClient(data)
      advance(true)
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => advance(false)

  // We render a thin custom shell around ClientForm so we can control button labels
  // ("Save & Next" / "Save & Finish") and a Skip action. ClientForm's own Cancel
  // is reused as the Skip handler.
  return (
    <div className="space-y-3">
      <div className="text-xs text-stone-500">
        Reviewing {index + 1} of {candidates.length} · <span className="font-mono">{current.domain}</span>
      </div>
      <ClientForm
        key={current.domain /* force-remount per candidate to reset internal state */}
        initialContacts={contactsFromCandidate(current)}
        initial={{
          id: '', slug: '', industry: null, size: null, contacts: contactsFromCandidate(current),
          notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '',
          name: current.suggested_name,
        }}
        onSubmit={handleSubmit}
        onCancel={handleSkip}
        saving={saving}
      />
      {/* Override the bottom button labels visually — ClientForm shows "Save" by default
          when `initial` is provided, so we add a hint chip below. */}
      <p className="text-xs text-stone-400">
        Submitting saves this client and {isLast ? 'finishes' : 'moves to the next candidate'}.
        Tap "Cancel" to skip without saving.
      </p>
    </div>
  )
}
```

> **Note on the test for button name:** the test uses regex `/save & next/i` and `/save & finish/i`. Since this implementation reuses `ClientForm` which always shows just "Save" or "Create client", we need to make the primary-button label configurable. **Modify** `ClientForm` to accept an optional `submitLabel?: string` prop (default behavior unchanged), and pass it from the wizard.

**Action:** Open `frontend/src/components/clients/client-form.tsx` and:

1. Add `submitLabel?: string` to the `Props` interface
2. Destructure it in the function signature
3. Update the submit button to use it:

```typescript
{saving ? 'Saving…' : (submitLabel ?? (initial ? 'Save' : 'Create client'))}
```

Then update the wizard's call:

```typescript
<ClientForm
  key={current.domain}
  initialContacts={contactsFromCandidate(current)}
  initial={{ ... as above ... }}
  onSubmit={handleSubmit}
  onCancel={handleSkip}
  saving={saving}
  submitLabel={isLast ? 'Save & Finish' : 'Save & Next'}
/>
```

And remove the now-redundant `<p>` hint at the bottom of the wizard.

Also update the wizard's bottom-of-screen "skip" affordance: ClientForm's Cancel button reads "Cancel". For the wizard context, we want it to read "Skip this". Add a `cancelLabel?: string` prop to ClientForm the same way as `submitLabel`, default unchanged, and pass `cancelLabel="Skip this"` from the wizard.

After both prop additions, the final ClientForm button JSX is:

```typescript
<div className="flex justify-end gap-2 pt-2">
  <button
    type="button"
    onClick={onCancel}
    className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
  >
    {cancelLabel ?? 'Cancel'}
  </button>
  <button
    type="submit"
    disabled={saving || !name.trim()}
    className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
  >
    {saving ? 'Saving…' : (submitLabel ?? (initial ? 'Save' : 'Create client'))}
  </button>
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx src/components/clients/__tests__/client-form.test.tsx`
Expected: PASS — 5 wizard tests + 4 form tests = 9 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/discovery/candidate-review-wizard.tsx \
        frontend/src/components/clients/discovery/__tests__/candidate-review-wizard.test.tsx \
        frontend/src/components/clients/client-form.tsx
git commit -m "feat(discovery): CandidateReviewWizard + configurable button labels on ClientForm"
```

---

## Task 11: ClientDiscoveryFlow state machine

**Files:**
- Create: `frontend/src/components/clients/discovery/client-discovery-flow.tsx`
- Create: `frontend/src/components/clients/discovery/index.ts` (barrel)
- Create: `frontend/src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../../test/mocks/server'
import { API } from '../../../../test/mocks/handlers'
import { renderWithProviders } from '../../../../test/utils'
import { ClientDiscoveryFlow } from '../client-discovery-flow'

const CANDIDATE_RESPONSE = {
  candidates: [{
    domain: 'acme.com', suggested_name: 'Acme',
    message_count: 47, sender_count: 2,
    top_senders: [{ name: 'Jane', email: 'jane@acme.com', message_count: 28 }],
    first_date: '2026-04-01T00:00:00Z', last_date: '2026-05-18T00:00:00Z',
  }],
  excluded_existing: 0,
  scanned_messages: 200,
  duration_seconds: 4.2,
}

describe('ClientDiscoveryFlow', () => {
  it('walks lookback → scanning → list → wizard → done', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json(CANDIDATE_RESPONSE),
      ),
      http.post(`${API}/clients`, async () =>
        HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '',
        }),
      ),
    )

    const onComplete = vi.fn()
    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={onComplete} />)

    // Step 1: lookback picker
    expect(screen.getByText(/look back how far/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /90 days/i }))

    // Step 2: scanning → list (candidate appears)
    await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument())

    // Select candidate and proceed to wizard
    await user.click(screen.getByRole('checkbox', { name: /select acme/i }))
    await user.click(screen.getByRole('button', { name: /review 1 selected/i }))

    // Step 3: wizard — save & finish (only one candidate)
    expect(await screen.findByText(/reviewing 1 of 1/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /save & finish/i }))

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith({ created: 1 }))
  })

  it('shows an error message when the discover call fails with 401', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json({ detail: 'Stored Gmail credentials could not be decrypted; please reconnect' }, { status: 401 }),
      ),
    )

    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))

    await waitFor(() => expect(screen.getByText(/please reconnect/i)).toBeInTheDocument())
  })

  it('Skip all in the candidate list calls onComplete with created=0', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json(CANDIDATE_RESPONSE),
      ),
    )
    const onComplete = vi.fn()
    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={onComplete} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))
    await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /skip all/i }))
    expect(onComplete).toHaveBeenCalledWith({ created: 0 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx`
Expected: FAIL — module-not-found.

- [ ] **Step 3: Write the component + barrel**

Create `frontend/src/components/clients/discovery/client-discovery-flow.tsx`:

```typescript
import { useState } from 'react'
import { useDiscoverClients } from '../../../api/discovery'
import { useCreateClient } from '../../../api/clients'
import { LookbackPicker } from './lookback-picker'
import { CandidateList } from './candidate-list'
import { CandidateReviewWizard } from './candidate-review-wizard'
import type { Candidate, DiscoveryResponse, LookbackDays } from '../../../types/discovery'
import type { ClientCreate } from '../../../types/client'

interface Props {
  open: boolean
  onClose: () => void
  onComplete: (summary: { created: number }) => void
}

type Phase =
  | { kind: 'lookback' }
  | { kind: 'scanning' }
  | { kind: 'list', response: DiscoveryResponse }
  | { kind: 'wizard', selected: Candidate[] }
  | { kind: 'error', message: string }

export function ClientDiscoveryFlow({ open, onClose, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'lookback' })
  const discover = useDiscoverClients()
  const createClient = useCreateClient()

  if (!open) return null

  const handlePickLookback = async (days: LookbackDays) => {
    setPhase({ kind: 'scanning' })
    try {
      const response = await discover.mutateAsync(days)
      setPhase({ kind: 'list', response })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setPhase({ kind: 'error', message: detail ?? 'Could not scan your inbox right now.' })
    }
  }

  const handleReview = (selected: Candidate[]) => {
    setPhase({ kind: 'wizard', selected })
  }

  const handleSkipAll = () => {
    onComplete({ created: 0 })
  }

  const handleSaveClient = async (data: ClientCreate) => {
    await createClient.mutateAsync(data)
  }

  const handleWizardComplete = ({ created }: { created: number }) => {
    onComplete({ created })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-lg">
        {phase.kind === 'lookback' && (
          <LookbackPicker onPick={handlePickLookback} onCancel={onClose} />
        )}
        {phase.kind === 'scanning' && (
          <div className="py-12 text-center">
            <p className="text-sm text-stone-500">Scanning your inbox…</p>
          </div>
        )}
        {phase.kind === 'list' && (
          <CandidateList
            response={phase.response}
            onReview={handleReview}
            onSkipAll={handleSkipAll}
          />
        )}
        {phase.kind === 'wizard' && (
          <CandidateReviewWizard
            candidates={phase.selected}
            onSaveClient={handleSaveClient}
            onComplete={handleWizardComplete}
          />
        )}
        {phase.kind === 'error' && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-stone-900">Couldn't scan your inbox</h2>
            <p className="text-sm text-stone-600">{phase.message}</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
              >
                Close
              </button>
              <button
                onClick={() => setPhase({ kind: 'lookback' })}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
              >
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

Create `frontend/src/components/clients/discovery/index.ts`:

```typescript
export { ClientDiscoveryFlow } from './client-discovery-flow'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm vitest run src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/discovery/client-discovery-flow.tsx \
        frontend/src/components/clients/discovery/index.ts \
        frontend/src/components/clients/discovery/__tests__/client-discovery-flow.test.tsx
git commit -m "feat(discovery): ClientDiscoveryFlow state machine"
```

---

## Task 12: Wire ClientDiscoveryFlow into /clients page

**Files:**
- Modify: `frontend/src/pages/clients/list.tsx`
- Extend or create: `frontend/src/pages/clients/__tests__/list.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create or extend `frontend/src/pages/clients/__tests__/list.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ClientListPage } from '../list'

describe('ClientListPage discovery integration', () => {
  it('empty state shows BOTH CTAs when Gmail is connected', async () => {
    server.use(
      http.get(`${API}/clients`, async () => HttpResponse.json([])),
      http.get(`${API}/connectors/gmail/status`, async () =>
        HttpResponse.json({ connected: true, email: 'me@veeville.com' }),
      ),
    )
    renderWithProviders(<ClientListPage />)
    await waitFor(() => expect(screen.getByText(/no clients yet/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /add a client manually/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /discover from gmail/i })).toBeInTheDocument()
  })

  it('empty state shows ONLY manual CTA when Gmail is not connected', async () => {
    server.use(
      http.get(`${API}/clients`, async () => HttpResponse.json([])),
      http.get(`${API}/connectors/gmail/status`, async () =>
        HttpResponse.json({ connected: false }),
      ),
    )
    renderWithProviders(<ClientListPage />)
    await waitFor(() => expect(screen.getByText(/no clients yet/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /add a client manually/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /discover from gmail/i })).not.toBeInTheDocument()
  })

  it('populated state shows the secondary Discover button when Gmail is connected', async () => {
    server.use(
      http.get(`${API}/clients`, async () => HttpResponse.json([
        { id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '' },
      ])),
      http.get(`${API}/connectors/gmail/status`, async () =>
        HttpResponse.json({ connected: true, email: 'me@veeville.com' }),
      ),
    )
    renderWithProviders(<ClientListPage />)
    await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^add client$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /discover from gmail/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/pages/clients/__tests__/list.test.tsx`
Expected: FAIL — "Discover from Gmail" button doesn't exist; empty-state copy differs.

- [ ] **Step 3: Update the page**

Open `frontend/src/pages/clients/list.tsx`. Make these changes:

1. Add the import:

```typescript
import { ClientDiscoveryFlow } from '../../components/clients/discovery'
import { useGmailStatus } from '../../api/connectors'   // if this hook exists; otherwise use the same call settings page makes — adapt the import
```

> **Note for implementer:** If `useGmailStatus` doesn't exist in `frontend/src/api/connectors.ts`, look at the Settings → Gmail connector card (`frontend/src/components/settings/gmail-connector-card.tsx`) for the pattern it uses to determine `gmail.connected`, and reuse the same hook here. Don't invent a new HTTP shape.

2. Add state for the discovery modal:

```typescript
const [discoveryOpen, setDiscoveryOpen] = useState(false)
const { data: gmailStatus } = useGmailStatus()
const gmailConnected = gmailStatus?.connected === true
const queryClient = useQueryClient()  // already imported? if not, add it
```

3. Define a completion handler that refreshes clients:

```typescript
const handleDiscoveryComplete = (_summary: { created: number }) => {
  setDiscoveryOpen(false)
  queryClient.invalidateQueries({ queryKey: ['clients'] })
}
```

4. Replace the empty state — the current "No clients yet." block — with:

```typescript
{clients?.length === 0 && !isLoading && (
  <div className="rounded-xl border border-dashed border-stone-300 bg-white p-8 text-center">
    <p className="text-sm text-stone-500 mb-4">No clients yet.</p>
    <div className="flex justify-center gap-2">
      <button
        onClick={() => setShowForm(true)}
        className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
      >
        Add a client manually
      </button>
      {gmailConnected && (
        <button
          onClick={() => setDiscoveryOpen(true)}
          className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
        >
          Discover from Gmail
        </button>
      )}
    </div>
  </div>
)}
```

5. Update the header (when clients exist) — replace the existing single "Add client" button with a button group:

```typescript
<div className="flex items-center gap-2">
  {gmailConnected && (
    <button
      onClick={() => setDiscoveryOpen(true)}
      className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
    >
      Discover from Gmail
    </button>
  )}
  <button
    onClick={() => setShowForm(true)}
    className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
  >
    Add client
  </button>
</div>
```

6. Mount the modal at the end of the component (next to the existing create-form modal):

```typescript
<ClientDiscoveryFlow
  open={discoveryOpen}
  onClose={() => setDiscoveryOpen(false)}
  onComplete={handleDiscoveryComplete}
/>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm vitest run src/pages/clients/__tests__/list.test.tsx`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/clients/list.tsx \
        frontend/src/pages/clients/__tests__/list.test.tsx
git commit -m "feat(discovery): wire ClientDiscoveryFlow into /clients page with empty-state + secondary CTAs"
```

---

## Task 13: Full sweep — backend + frontend + build + lint

**Files:** No source changes. Verification only.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green. Tally = previous baseline + new discovery tests (~25 new across aggregator, ViewModel, endpoint).

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && pnpm test`
Expected: all green. Tally = 223 (post-rate-card baseline) + ~25 new discovery tests = ~248.

- [ ] **Step 3: Typecheck + frontend build**

Run: `cd frontend && pnpm build`
Expected: clean build, no TS errors.

- [ ] **Step 4: Lint**

Run: `cd frontend && pnpm lint`
Expected: no NEW errors. The 4 pre-existing errors in S2/S3 OAuth-callback / context-brief-toggle files remain as known tech debt; the new files contribute none. If any new file shows a lint error, fix and re-commit before declaring done.

- [ ] **Step 5: Manual smoke test (optional but recommended)**

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000 &
cd frontend && pnpm dev
```

In the browser:
1. Log in
2. If clients exist, delete them all (or use a fresh agency)
3. Visit /clients — empty state should show TWO CTAs (assuming Gmail is connected; else only "Add a client manually")
4. Click **Discover from Gmail** → lookback modal appears
5. Pick **90 days** → spinner → candidate list
6. Tick 2 candidates → click **Review 2 selected** → wizard appears with first pre-filled
7. Edit name if you want → click **Save & Next** → second candidate appears
8. Click **Save & Finish** → modal closes, /clients list refreshes showing the new clients

- [ ] **Step 6: Final commit if any fixes from steps 1-4**

If lint or build needed cleanup:

```bash
git add <fixed files>
git commit -m "fix(discovery): <one-line description of follow-up>"
```

If everything green: no commit needed.

---

## Acceptance Recap

Verify against spec acceptance criteria (`docs/superpowers/specs/2026-05-19-client-discovery-from-gmail-design.md`):

- ✓ `POST /api/v1/connectors/gmail/discover-clients` exists, accepts `{lookback_days: 30 | 90 | 365}` (Task 5)
- ✓ Endpoint returns `DiscoveryResponse` shape (Task 1 schemas, Task 5 integration test)
- ✓ Aggregator filters freemail + SaaS noise + own-domain + no-reply + already-linked (Task 2 unit tests)
- ✓ Sort: message_count desc, last_date desc tiebreaker (Task 2 unit test)
- ✓ Empty state shows both CTAs when Gmail connected; only "Add client" otherwise (Task 12)
- ✓ Populated state shows primary + secondary buttons when Gmail connected (Task 12)
- ✓ Flow: lookback → scanning → list → wizard → done (Task 11 integration test)
- ✓ Wizard pre-fills name (heuristic) + contacts (top 3 senders) (Task 10)
- ✓ ClientForm supports `initialContacts` + inline contacts editor (Task 7)
- ✓ After completion, /clients list refreshes (Task 12 `invalidateQueries`)
- ✓ `pnpm test`, `pytest`, `pnpm build` all green (Task 13)

## Deferred from spec (future work, documented)

- LLM-powered company naming (opt-in batch via Haiku 4.5)
- Industry / size auto-detection from email content
- Background scheduled discovery cron
- Per-agency configurable noise list
- Pagination of existing-client check for agencies with 500+ clients
- Wizard "back" button to revisit a previously-saved candidate
- Slack-side discovery analogue
