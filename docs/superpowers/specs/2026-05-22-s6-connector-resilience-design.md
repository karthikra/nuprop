# S6 — Connector Resilience & Backend Hardening — Design

**Status:** Brainstormed 2026-05-22. Implementation plan: pending.
**Surfaces:** `backend/` only — the 4 connector HTTP clients, connector viewmodel, gmail client pagination, the LLM client, and `client_repo`. No frontend changes, no schema change.
**Slice:** S6 of the M16-M20 roadmap (S1-S5 complete). This is the last roadmap slice; it is deferrable and does not block users.

---

## Goal

S1 closed the M16-M20 CRITICAL findings (fail-loud encryption, OAuth CSRF, module-level logging, narrowed `except` blocks). The connector subsystem works but is **fragile under provider failure**: there is zero retry/backoff anywhere, so a single `429` or `503` from Google or Slack fails an entire sync. S6 makes the connector calls resilient and closes the remaining audit-flagged HIGH backend hardening items.

This is intentionally a tight, ~1-day resilience slice — no new features, no behavior change visible to users beyond "syncs that used to fail on a transient error now succeed."

## Non-goals

- **Rate limiting.** The audit listed it; dropped here. Syncs are user-triggered (a "Sync Now" button), low-volume, and providers enforce their own quotas. Once retry/backoff absorbs provider `429`s, app-level rate limiting is redundant for current scale. Revisit only if abuse appears.
- **The 3 frontend follow-ups** the handoff parked under "S6" — ContextBriefToggle cache surviving invalidation (S2 follow-up), `getAuthUrl.isError` / `disconnectSlack.isError` surfacing in connector cards (S3 follow-up), and the rate-card wizard's timed skip-notice. These are frontend and become a separate **S7** slice. S6 is backend-only, matching the audit's original definition.
- **`pricing_model` branching** in `CostModelBuilder`. S5 carries the key through the merged config but nothing branches on it. Making it do something is a fresh design conversation ("what *is* the alternative pricing model?") — not resilience polish.
- **Real client-list pagination** (cursor/offset across backend + frontend). S6 only raises the `client_repo` default cap; proper pagination is a future slice if an agency nears the ceiling.
- **No schema change.** Migration head stays at `03_proposal_context_brief`.

## Current state (from codebase exploration)

- **Connector HTTP clients** — `gmail_client.py`, `gdrive_client.py`, `gcal_client.py`, `slack_client.py` — each call opens its own `async with httpx.AsyncClient()`, issues the request, and calls `raise_for_status()`. There is **no retry** anywhere (`grep tenacity` → 0 hits). Timeouts are inconsistent: `slack_client` passes `timeout=10`/`15` on some calls; the Gmail and Drive/Calendar calls pass none, so a hung connection has no bound.
- **Gmail pagination** — `gmail_client.py:165` (`fetch_messages_for_domain`) and `:209` (`fetch_recent_messages`) both loop `while len(all_messages) < limit`. S1 added `if not page_token: break`, so the common termination case is handled. Residual risk: if Google returns 0 messages but a non-null `pageToken` repeatedly, `len < limit` never trips and the loop runs unbounded.
- **Email parsing** — re-checking the code: `connector_viewmodel.py:258-259` is *already* guarded (`if _email and "@" in _email`). Only `_extract_domains` at `:495` (`email.split("@")[-1]`) is unguarded. Separately, `gmail_client.py:142` falls back to a naive `datetime.now()` when an email `Date` header is unparseable — disguising the parse failure as a plausible timestamp, and producing a timezone-naive value that flows into the `DateTime(timezone=True)` `EmailIndex.date` column.
- **LLM calls** — `context_service.py` reaches Bedrock via `AnthropicClient()`, which is a thin facade over `AIService` (`app/services/llm.py`). `AIService.__init__` constructs `AsyncAnthropicBedrock(**kwargs)` with no `timeout` — a hung call stalls the whole pipeline phase (each phase is its own ARQ job).
- **`client_repo.search`** — default `limit=50` (`client_repo.py:23`). Agencies with >50 clients silently lose the tail; the frontend client list does not paginate.

## Architecture

### Piece A — Shared retry wrapper

New module `backend/app/infrastructure/external/_retry.py` exposing one async helper:

```
async def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = 30.0,
    max_attempts: int = 4,
    **kwargs,
) -> httpx.Response
```

The `timeout` default is `30.0` seconds; callers that already pass their own (`slack_client` uses 10/15) keep overriding it.

It owns the full request lifecycle currently copy-pasted across the four clients — open `httpx.AsyncClient`, issue the request, `raise_for_status()` — and adds:

- **Retryable failures:** HTTP `429`, `500`, `502`, `503`, `504`, and `httpx.TransportError` (connection errors, read/connect timeouts).
- **Terminal failures (never retried):** all other 4xx — most importantly `401` / `invalid_grant` auth failures. These must propagate unchanged so the existing connector behavior (return 400 not 401, see the global-401-interceptor gotcha) and S5's per-client error isolation in `sync_emails` / `enrich_context_from_emails` continue to work.
- **Backoff:** exponential with jitter between attempts. When the response carries a `Retry-After` header, honor it instead of the computed backoff.
- **Uniform timeout:** a sane default applied to every call, closing the current no-timeout gap on the Gmail/Drive/Calendar requests.
- **Logging:** a structured warning per retry attempt (`event: connector.retry`), a structured error on final exhaustion before the exception propagates.

Internally the module may use `tenacity` for the backoff curve; the design point is that this module is the *single* policy definition — the four clients become thin call sites.

**Migration of the four clients:** each `async with httpx.AsyncClient() as client: r = await client.{get,post}(...); r.raise_for_status()` block is replaced with a `request_with_retry(...)` call. No change to client method signatures or return types — callers (the connector viewmodel) are unaffected.

### Piece B — Hardening fixes

| Fix | Location | Change |
|---|---|---|
| Pagination max-iterations guard | `gmail_client.py:165`, `:209` | Add a hard iteration cap to both `while` loops — a fixed `MAX_PAGE_ITERATIONS = 50` (comfortably above any real `limit / batch_size`). If hit, log a structured warning and `break` — bounds the 0-results-plus-non-null-`pageToken` case. |
| Email `@` validation | `connector_viewmodel.py:495` (`_extract_domains`) | Guard `email.split("@")[-1]` — skip entries without a valid `@`. Line 259 is already guarded; only `_extract_domains` needs the fix. |
| Email date parsing | `gmail_client.py:142` (`get_message`) | On an unparseable `Date` header, return `date=None` instead of a naive `datetime.now()`. `EmailIndex.date` is `NOT NULL`, so the persisted value still gets a fallback — but at the *one* existing coercion point (`connector_viewmodel.py:324`, `… else now` where `now` is timezone-aware). Net effect: the failure stops being disguised as a plausible per-message timestamp, the naive-datetime bug is removed, and the `connector.gmail.bad_date` log is the audit trail. No schema change. |
| LLM call timeout | `app/services/llm.py` — `AIService.__init__` | Pass an explicit `timeout` to `AsyncAnthropicBedrock(**kwargs)` so a hung Bedrock call cannot stall a pipeline phase. (`AnthropicClient` is only a facade — the real client lives here.) |
| `client_repo` cap | `client_repo.py:23` | Raise the default `limit` from 50 to 500. One-line change, no API-shape change. |

## Error handling

S6's whole purpose is error handling, so the contract is explicit:

- **Transient provider errors** (`429`/`5xx`/transport) are retried up to `max_attempts`, then the exception propagates. The connector viewmodel's existing per-client `try/except` (S1 + S5) catches it, logs, and continues with the next client — one bad client no longer aborts the sync.
- **Auth errors** (`401`/`invalid_grant`) are *not* retried — propagated immediately so stale-credential handling and the 400-not-401 connector contract still fire.
- **Pagination cap hit** is a logged warning, not an error — the sync proceeds with whatever was collected.
- **Malformed email field** is logged and skipped/null-stored — never crashes the sync, never corrupts the `context_profile` JSON column.

## Testing

- **Retry wrapper** (unit, mocked `httpx` transport): `429`-then-`200` retries and succeeds; `Retry-After` header honored; `invalid_grant` / `401` raises immediately with no retry; exhaustion after `max_attempts` raises; transport error retried.
- **Pagination guard:** loop terminates when the iteration cap is hit even with a perpetually non-null page token.
- **Email parsing:** malformed email address and unparseable date are handled without crashing and without corrupting the JSON column.
- **LLM timeout:** a call exceeding the timeout raises rather than hanging.
- **Regression:** the existing 339 backend tests stay green. Frontend untouched (247 stay green). Migration head unchanged.

## Future work

- **S7** — the 3 deferred frontend follow-ups listed under Non-goals.
- Real client-list pagination (backend `limit`/`offset` + a paginating frontend) when an agency approaches the 500 cap.
- `pricing_model` branching — its own design conversation.
- Retry/backoff for Bedrock LLM calls (S6 only adds a timeout there; a retry policy for Bedrock could follow the same wrapper pattern).
