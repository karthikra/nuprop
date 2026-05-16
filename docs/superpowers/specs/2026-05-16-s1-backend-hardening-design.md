# Spec — S1: M16-M20 Backend Hardening (CRITICAL fixes)

**Date:** 2026-05-16
**Slice:** S1 of S0-S6 M16-M20 finish-line (see [audit](../audits/2026-05-16-m16-m20-state-audit.md))
**Worktree:** `m16-m20-s1-backend-hardening`
**Owner:** Karthik
**Estimate:** 1 day
**Status:** spec — awaiting approval

---

## Goal

Make the existing M16-M20 backend code safe to enable in production. Today the code "works" against happy-path tests but has 5 CRITICAL security and observability holes that would either leak refresh tokens, brick all stored tokens on key rotation, allow OAuth CSRF, lose every email on a sync exception, or silently hide every failure. **This slice closes those holes only.** HIGH/MEDIUM polish and frontend work are deferred to S2/S3/S6.

---

## What "shipped" looks like

After S1 merges to `main`, all of the following are true:

1. **Encryption fails loud, not silent.** Starting the app with connectors enabled but `ENCRYPTION_KEY` unset raises a clear startup error. Decryption errors (e.g., after key rotation) log a structured error and force the user back through OAuth, never crashing a request handler.
2. **OAuth CSRF closed.** Both Gmail and Slack OAuth flows generate a signed, time-limited `state` token at `/auth-url` and verify it on `/callback`. Replayed or forged states return `400 invalid_state` and write an audit log line.
3. **Every M16-M20 file has a module-level logger.** No `except: pass` anywhere in M16-M20 backend; each `except` either re-raises, logs via `logger.exception(...)`, or returns a structured error the caller surfaces.
4. **Services injected, not instantiated in route handlers.** `ContextService` and `ConnectorViewModel`-internal external clients use FastAPI `Depends()`; route handlers stay thin.
5. **Email sync survives partial failures.** Bulk insert commits per domain (or per ≤50-row batch). A mid-sync exception preserves what's already committed and the next sync resumes from the correct watermark.
6. **Tests cover each fix.** `test_connector_encryption.py`, `test_connector_oauth_state.py`, `test_email_sync_resumption.py`, plus negative tests for each `except` branch. Pytest stays at 100% pass.
7. **No backwards-incompatible API changes.** Frontend (sparse as it is today) continues to compile and pass vitest. Behavior changes are additive (new validations) or error-message-only.

Non-goals for S1 (explicitly):
- Frontend UI work (S2/S3).
- Pipeline integration (S5).
- Retry/backoff for external APIs (S6).
- Pagination loop bound, email parsing validation, malformed-date fix (S6).
- HIGH-severity issues not listed above (S6).

---

## Architecture decisions

### D1 — Encryption: fail-loud at startup, not silent fallback

**Current:** `connector_viewmodel.py:53-65` silently returns plaintext if `ENCRYPTION_KEY` is empty.

**Change:**
- Move encryption into a small `app/infrastructure/security/token_vault.py` module with `encrypt(text: str) -> str`, `decrypt(text: str) -> str`, and `is_configured() -> bool`.
- At app startup (`app/main.py` lifespan), if any connector env vars are populated (`GOOGLE_CLIENT_ID` or `SLACK_CLIENT_ID`) and `ENCRYPTION_KEY` is empty, raise `RuntimeError` and refuse to boot. The check is opt-in: dev environments without connector creds still start.
- `decrypt()` catches `cryptography.fernet.InvalidToken`, logs a structured warning, and raises `app.core.errors.TokenVaultError`. Callers in `ConnectorViewModel` catch `TokenVaultError`, mark the connector as `needs_reauth=True`, return a friendly "please reconnect" error to the route.
- `encrypt()` never falls back to plaintext. If called without configuration, raises `TokenVaultError` — but the startup check should make that unreachable in practice.

**Why:** Plaintext-in-prod silently is the worst failure mode. A loud boot error is loud once; silent plaintext is loud only in the post-breach RCA. Decryption failures after key rotation are recoverable (re-auth), not crashes.

**Test surface:** `test_token_vault.py` — encrypt/decrypt roundtrip, decrypt of garbage raises `TokenVaultError`, decrypt with wrong key raises `TokenVaultError`. Plus a startup-validation test in `test_app_startup.py`.

### D2 — OAuth state: signed, time-limited, single-use

**Current:** `connector_viewmodel.py:69-99` sets `state = str(agency_id)` on `/auth-url` and never verifies it on callback.

**Change:**
- New module `app/core/oauth_state.py` with two functions:
  - `issue_state(agency_id: UUID, provider: str, ttl_seconds: int = 600) -> str` — returns a base64url-encoded JSON payload `{agency_id, provider, nonce, iat, exp}` signed with HMAC-SHA256 using `JWT_SECRET_KEY` (already a Fly secret).
  - `verify_state(token: str, expected_provider: str) -> UUID` — verifies signature, checks `exp`, checks `provider` matches, returns `agency_id`. Raises `OAuthStateError` on any mismatch.
- ConnectorViewModel `/auth-url` handlers issue state for the requesting agency. `/callback` handlers verify it and use the returned agency_id (do not trust the URL path or session for agency_id during callback).
- Replay protection: store consumed nonces in Redis with the same TTL as the state's expiry; reject a state whose nonce is already in the set. Use `SET nonce "" EX 600 NX`.

**Why:** This is the standard OAuth state pattern. JWT_SECRET_KEY is already deployed; reusing it keeps the moving parts to one secret. Redis is already in the stack — nonce dedup is one `SET NX EX` per callback. 10-minute TTL covers slow human flows without leaving wide replay windows.

**Test surface:** `test_oauth_state.py` — issue/verify roundtrip, wrong-provider rejected, expired rejected, tampered rejected, replayed nonce rejected. Plus integration tests `test_gmail_callback_rejects_bad_state.py` and `test_slack_callback_rejects_bad_state.py`.

### D3 — Logging: module-level loggers, narrowed excepts, structured fields

**Current:** Zero `logging` imports across M16-M20 backend. Every `except` is a bare `pass` or `continue`.

**Change:**
- Add `logger = logging.getLogger(__name__)` to every file in: `services/context_service.py`, `services/context_intelligence.py`, `viewmodels/connector_viewmodel.py`, `infrastructure/external/gmail_client.py`, `infrastructure/external/gdrive_client.py`, `infrastructure/external/gcal_client.py`, `infrastructure/external/slack_client.py`, `infrastructure/db/repositories/email_index_repo.py`.
- Replace every M16-M20 `except Exception: pass` / `except Exception: continue` with one of:
  - `except SpecificError as e: logger.warning("...", extra={"field": value}); continue` — for known-recoverable failures (e.g., malformed Gmail date).
  - `except SpecificError as e: logger.exception("..."); raise` — for unexpected failures we want to propagate.
  - `except SpecificError as e: logger.exception("..."); return structured_error(...)` — for surfaces that must return something.
- New helper `app/core/errors.py` exposing the small set of M16-M20-specific exceptions: `TokenVaultError`, `OAuthStateError`, `ConnectorAuthError`, `ConnectorSyncError`. Each carries `code`, `message`, optional `cause`.
- Audit log line for security events (state-mismatch, token-decryption-failure, replay-attempt) — same logger but with `extra={"event": "security.<name>"}` so future log aggregation can filter.

**Why:** No logging = no production debugging. The narrowed-except pattern is what the project already uses elsewhere (see `pipeline_service.py:90-92` for `_load_context_brief`). Custom error classes keep route handlers' `try/except` short.

**Test surface:** Each negative test asserts the log message via `caplog` and the structured `extra` fields.

### D4 — DI: services injected via FastAPI `Depends()`

**Current:** `clients.py:95, 127` does `from app.services.context_service import ContextService; svc = ContextService()` inline.

**Change:**
- New helpers in `app/core/deps.py` using `@functools.lru_cache(maxsize=1)` for process-level singletons (the service is stateless except for the `AnthropicClient`, which is itself singleton-safe):
  - `def get_context_service() -> ContextService:` 
  - `def get_token_vault() -> TokenVault:` 
- Update `clients.py` and `connectors.py` route handlers to take `ctx: ContextService = Depends(get_context_service)` parameters.
- Update `ConnectorViewModel.__init__` to accept `gmail_client: GmailClient | None = None` etc., defaulting to fresh instances if not provided — this keeps prod behavior unchanged but lets tests inject mocks.

**Why:** Matches the project's MVVM/DI pattern (see how `chat_viewmodel.py` is constructed). Makes mocking trivial. Removes a small per-request allocation.

**Test surface:** Update existing test that hits `POST /clients/{id}/context` to override the dependency. New test that asserts the override works.

### D5 — Email sync: commit per domain, watermark per domain

**Current:** `connector_viewmodel.py:194-214` loops `db.add(email)` then relies on the route handler's `get_db()` to commit. A failure between the loop and the route handler's commit loses every email in the batch.

**Change:**
- Move email persistence into a new method `EmailIndexRepository.upsert_many(rows: list[EmailIndexCreate]) -> int` that commits in chunks of 50.
- In `ConnectorViewModel.sync_emails`, process one domain at a time. After each domain's emails are persisted, write the new watermark and commit. The watermark lives in `client.context_profile._sources.gmail.last_sync_per_domain` as `dict[str, str]` mapping `domain -> ISO timestamp of newest email persisted`. If a later domain raises, the prior domains' work is preserved and the next sync resumes from that domain's individual watermark.
- Keep the existing `_sources.gmail.last_sync` field, set it to `min(last_sync_per_domain.values())` for backwards-compat with `compute_quality_score` which reads the coarse field today.

**Why:** Resumption from a single watermark loses data on partial failure. Per-domain watermarks bound the loss to "one domain's emails" not "every email since the last successful full sync". 50-row chunks balance commit overhead against rollback blast radius.

**Test surface:** `test_email_sync_resumption.py` — set up two domains, raise after the first, assert first domain's emails are persisted and second's are skipped; rerun, assert second is now picked up from the correct watermark.

---

## File-by-file change list

| File | Change |
|---|---|
| `backend/app/infrastructure/security/__init__.py` | new, empty |
| `backend/app/infrastructure/security/token_vault.py` | new — `encrypt`, `decrypt`, `is_configured`, fails loud |
| `backend/app/core/oauth_state.py` | new — `issue_state`, `verify_state` (HMAC + Redis nonce dedup) |
| `backend/app/core/errors.py` | new — `TokenVaultError`, `OAuthStateError`, `ConnectorAuthError`, `ConnectorSyncError` |
| `backend/app/core/deps.py` | additions — `get_context_service`, `get_token_vault` |
| `backend/app/main.py` | lifespan addition — validate `ENCRYPTION_KEY` if connectors enabled |
| `backend/app/services/context_service.py` | add logger, narrow excepts, log on `enrich_context_with_emails` failure (line 227) |
| `backend/app/services/context_intelligence.py` | add logger, narrow date-parse excepts (lines 88, 103) |
| `backend/app/viewmodels/connector_viewmodel.py` | replace `_encrypt`/`_decrypt` with `token_vault` calls; rewrite `sync_emails` for per-domain commit; integrate `oauth_state`; add logger throughout; accept injected `gmail_client` / `slack_client` |
| `backend/app/infrastructure/external/gmail_client.py` | add logger; narrow excepts in `exchange_code`, `refresh_access_token`, `revoke`, `fetch_messages_for_domain` |
| `backend/app/infrastructure/external/slack_client.py` | add logger; narrow `exchange_code` excepts |
| `backend/app/infrastructure/external/gdrive_client.py` | add logger; narrow export-failure except (line 49) |
| `backend/app/infrastructure/external/gcal_client.py` | add logger |
| `backend/app/infrastructure/db/repositories/email_index_repo.py` | add `upsert_many(rows)` chunked-commit method |
| `backend/app/views/v1/clients.py` | route handlers take `ctx: ContextService = Depends(get_context_service)` instead of inline construction |
| `backend/app/views/v1/connectors.py` | route handlers verify state via `oauth_state.verify_state` (or pass the request body unchanged for backwards-compat — see Open Q3) |
| `backend/tests/unit/test_token_vault.py` | new |
| `backend/tests/unit/test_oauth_state.py` | new |
| `backend/tests/unit/test_app_startup.py` | new — assert startup fails loud when connector creds set but no ENCRYPTION_KEY |
| `backend/tests/integration/test_gmail_oauth_csrf.py` | new — callback rejects bad/expired/replayed state |
| `backend/tests/integration/test_slack_oauth_csrf.py` | new — same for Slack |
| `backend/tests/integration/test_email_sync_resumption.py` | new — per-domain commit + watermark |
| `backend/tests/integration/test_clients_context_di.py` | new — override `get_context_service` dependency works |

Total: ~7 new files, ~13 modified files, ~6 new test files. No frontend changes.

---

## Open questions for review

**Q1 — Should `ENCRYPTION_KEY` be a separate Fly secret or piggyback `JWT_SECRET_KEY`?**

Recommended: **separate.** Different rotation schedules, different blast radius (rotating JWT logs everyone out; rotating ENCRYPTION_KEY bricks every stored token). Separate is the right answer even if it's "one more thing to set in S4".

**Q2 — Do we add a `connectors_enabled: bool` Pydantic setting or detect from presence of `GOOGLE_CLIENT_ID`?**

Recommended: **detect from presence of creds.** Simpler, no extra setting to forget. If `GOOGLE_CLIENT_ID` is set, Google connectors are "enabled"; same for `SLACK_CLIENT_ID`. The startup check requires `ENCRYPTION_KEY` if EITHER is set.

**Q3 — Replay-prevention storage: Redis only, or also a Postgres `oauth_nonce` table for audit?**

Recommended: **Redis only.** Postgres adds latency to the OAuth callback (already slow). Redis TTL is good enough; the audit log captures the security event.

**Q4 — Logging format: structured JSON via stdlib, or use `structlog`?**

Recommended: **stdlib for now.** The project doesn't currently use structlog; adding it now grows scope. Use `logger.warning("msg", extra={...})` and rely on Fly's log forwarding to capture the extras. Migrate to structlog when the broader logging story is rewritten (out of scope here).

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Breaking change to OAuth `state` format breaks an in-flight OAuth flow at deploy time | Low | OAuth flows are seconds-long; deploy during low-usage window. New `state` is backwards-incompatible BY DESIGN (old states are unsigned, must be rejected). |
| Per-domain commits introduce a deadlock or session-scope confusion under load | Low | Tests cover the commit pattern; `AsyncSession` is per-request so no cross-request contention. |
| Adding a logger import per file inflates cold-start cost | Negligible | `logging.getLogger` is constant-time and idempotent. |
| Fail-loud startup blocks a deploy if `ENCRYPTION_KEY` isn't set but connectors are enabled | This is the desired behavior | Document in HANDOFF. S4 sets the secret as the first step of production OAuth wiring. |

---

## Acceptance test checklist (post-implementation)

- [ ] `cd backend && .venv/bin/python -m pytest -q` → 244 + (≥18 new tests, all passing). No skipped.
- [ ] `cd frontend && pnpm test --run` → 131 passed, no regressions.
- [ ] `grep -rn "except Exception" backend/app/{services/context*,viewmodels/connector_viewmodel.py,infrastructure/external/g*,infrastructure/external/s*}` returns either no results, or only narrowed-and-logged variants.
- [ ] `grep -rn "^import logging\|^from logging" backend/app/{services/context*,viewmodels/connector_viewmodel.py,infrastructure/external/g*,infrastructure/external/s*}` shows logging imported in every M16-M20 file.
- [ ] Manual: start the app locally with `GOOGLE_CLIENT_ID` set and `ENCRYPTION_KEY` unset → server refuses to start with a clear error message naming the missing var.
- [ ] Manual: trigger Gmail callback with a forged state → returns `400 invalid_state` with no token exchange attempted.

---

## What lands next (S2 preview)

After S1 merges and the user approves: open worktree `m16-m20-s2-context-ui`, write spec for the Manual Context UI on Client Detail page, implement, test, ship. Aims to be 1 day.
