# NUPROP Session Handoff

**Last updated:** 2026-05-21 (client discovery from Gmail shipped + deployed; S4 P6 smoke + secret rotation STILL open)
**Latest commit on `main`:** `4b62a82` (venv-symlink cleanup) on top of `1ef5d41` (client-discovery merge commit). Pushed; auto-deploy run `26207988191` triggered.
**Working tree:** clean. On `main`. In sync with `origin/main`.
**Production:** **LIVE at https://nuprop.fly.dev** — health 200, all 13 secrets deployed. As of this session: **Gmail-driven client discovery** live on the `/clients` page; rate-card wizard live in onboarding step 2 (since 2026-05-18).

## 🛑 START HERE NEXT SESSION

**Three browser-only smoke tests are pending. All shipped to prod, none ever clicked.** Do them in this order:

### 1. S4 P6 — OAuth connector smoke (open since 2026-05-17)

Open https://nuprop.fly.dev → register (use `karthik.ramesh@veeville.com` or `@example.com`, NOT `.local` — Pydantic rejects it) → Settings. Walk through these 6 checks in order:

| # | Action | Expected |
|---|---|---|
| 1 | Click **Connect Gmail** | Popup → accounts.google.com → Allow → `/settings/gmail-callback` → "Gmail connected" → closes → parent shows your Gmail address + green Connected badge |
| 2 | Click **Connect Slack** | Popup → slack.com/oauth/v2/authorize → Allow → `/settings/slack-callback` → "Slack connected" → closes → parent shows workspace name |
| 3 | **Drive** card → Sync Now | ~5s → green "Found X documents across Y clients" |
| 4 | **Calendar** card → Sync Now | ~5s → green "Found X meetings across Y clients" |
| 5 | **Gmail** card → Sync Now | ~15s (LLM classifies) → success alert. ⚠️ Returns "0 emails" if you have NO clients yet — Gmail sync searches BY client domain (see "Gmail sync needs clients first" gotcha below) |
| 6 | **Slack** card → Sync | ~10s → green "Found X mentions across Y clients" |

Debugging: `fly logs -a nuprop | grep -iE "connector|oauth|encrypt" | tail -20`

Common gotchas:
- Popup blocker — allow popups for `nuprop.fly.dev`
- Google `redirect_uri_mismatch` — must be exactly `https://nuprop.fly.dev/settings/gmail-callback` (no trailing slash)
- Slack "Invalid OAuth state" — S1's 10-min nonce TTL elapsed; click Connect again
- Drive/Cal "Google not connected" — do Gmail first

### 2. Client discovery smoke (NEW this session — shipped, never browser-tested)

The discovery flow scans your Gmail inbox to find candidate clients. Requires Gmail connected (step 1 above). Go to `/clients`:

| Action | Expected |
|---|---|
| Visit `/clients` with **0 clients** + Gmail connected | Empty state shows TWO buttons: "Add a client manually" + "Discover from Gmail" |
| Click **Discover from Gmail** | Modal: "Look back how far?" with 30 / 90 / 365-day buttons (90 highlighted) |
| Pick a window | Spinner "Scanning your inbox…" (~3-20s depending on window) → candidate list |
| Candidate list | One checkbox row per discovered domain: name guess, domain, email count, sender count, date range. Noise (freemail, github/linear/etc., no-reply, your own veeville.com) is filtered out |
| Tick candidates → **Review N selected** | Sequential wizard: pre-filled ClientForm per candidate (name = domain guess, contacts = top senders). "Save & Next" / "Save & Finish" / "Skip this" |
| After last candidate | "Created N clients" confirmation → Done → `/clients` list refreshes |
| Populated `/clients` + Gmail connected | Header shows secondary "Discover from Gmail" button next to "Add client" |

Debugging: `fly logs -a nuprop | grep -iE "discovery|connector" | tail -20`

### 3. Rate-card wizard smoke (open since 2026-05-18 — shipped, never browser-tested)

During registration you hit onboarding step 2 — the 4-sub-step rate-card wizard (Offerings / Hourly Rates / Multipliers / Globals). Walk all 4 sub-steps; every "Skip this section" advances; on 2d "Skip" submits like Finish. Detail matrix in git history (`docs/superpowers/HANDOFF.md` at commit `eafc47f` if you need the full per-substep checklist).

## 🔐 After smoke tests pass — rotate secrets (chat exposure cleanup)

Three secrets were pasted into AI chat transcripts during S4 P4 and need rotation:
- `GOOGLE_CLIENT_SECRET=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`
- `SLACK_CLIENT_SECRET=fdf51ff06cedda29a2f0c27cd1f59415`
- `ENCRYPTION_KEY=t6TjRRsjv8rqhpDf2M-kRFnhw9MGuVx9wBCu5vIYeIk=`

Short version (full step-by-step in the 2026-05-18 conversation history):

1. **Google:** https://console.cloud.google.com/apis/credentials → NUPROP Web Client → **Add secret** (don't reset — keep old enabled until rolling deploy confirms)
2. **Slack:** https://api.slack.com/apps → NUPROP → Basic Information → App Credentials → **Regenerate**
3. **Fernet:** `backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`
4. **Atomic push** (must be ONE command — S1 lifespan refuses to start if OAuth creds present without ENCRYPTION_KEY):
   ```bash
   fly secrets set -a nuprop \
     GOOGLE_CLIENT_SECRET="<new>" \
     SLACK_CLIENT_SECRET="<new>" \
     ENCRYPTION_KEY="<new fernet>"
   ```
5. ⚠️ ENCRYPTION_KEY rotation invalidates ALL stored Gmail + Slack tokens (`connector_viewmodel.py` — both Gmail refresh tokens and Slack access tokens use the vault). After rotation, **disconnect** existing Gmail + Slack in Settings first (avoids decrypt_failed alert), then **reconnect**.
6. Disable the old Google client secret only after re-auth confirms working.

## After all that — pick next slice

### Cleanup (5 min)

4 stale worktrees from prior sessions are still on disk:
```bash
git worktree remove .claude/worktrees/m16-m20-s1-backend-hardening
git worktree remove .claude/worktrees/m16-m20-s2-context-ui
git worktree remove .claude/worktrees/m16-m20-s3-connector-frontend
git worktree remove .claude/worktrees/m16-m20-s4-prod-oauth
git worktree prune
```
All 4 are already merged into main. Delete the branches too if you want: `git branch -D worktree-m16-m20-s1-backend-hardening` etc.

### S5 — Pipeline integration (~1.5d, all backend)

The biggest semantic slice in the M16-M20 roadmap. Goal: make the proposal pipeline actually CONSUME the context + connector data S1-S4 set up.

Open questions to brainstorm:
- Which of the 5 unwired pipeline phases get `context_brief` access first? (analyze_brief, run_research, run_benchmarks, build_cost_model, generate_narrative — only `run_ideation` consumes it today)
- Should `build_cost_model` read `proposal.preferences` directly, or via a normalized lookup in PipelineContext?
- Post-sync email auto-enrichment — trigger via webhook from connector sync, or a separate ARQ job?

Suggested next-session opener: invoke `superpowers:brainstorming` with target "wire context_brief and connector data into the 5 unwired pipeline phases (S5)".

### S6 — Backend polish (~1d, deferrable)

- ContextBriefToggle local cache survives invalidation (S2 follow-up)
- `getAuthUrl.isError` / `disconnectSlack.isError` surfacing in connector cards (S3 follow-up)
- Yellow-notice timed strip for the rate-card wizard's soft-required skip (`docs/superpowers/specs/2026-05-18-rate-card-form-design.md`)

### Client-discovery follow-ups (deferred, documented in its spec)

- LLM-powered company naming (heuristic-only today — `acme.com` → `Acme`, `tatacomms.com` → `Tatacomms`)
- Industry/size auto-detection from email content
- Background scheduled discovery cron
- `sync_emails` still returns **401** for stale Gmail creds (only `discover_clients` was fixed to **400** — the global axios 401-interceptor logs the user out, see lesson #2 below). `sync_emails` should get the same 400 treatment in a small follow-up.

---

## What happened this session (2026-05-21)

Shipped **client discovery from Gmail** end-to-end: brainstorm → spec → 13-task plan → subagent-driven execution → final review → `--no-ff` merge → push → deploy.

The feature solves a chicken-and-egg problem found while debugging "Gmail connector gives me zero mails": Gmail sync searches BY client domain, so a fresh agency with no clients gets 0 results forever. Discovery flips it — scan the inbox, propose candidate clients, bulk-create them.

### This session's commits (on main, deployed)

```
4b62a82 fix: drop accidentally-committed backend/.venv symlink, harden gitignore
1ef5d41 Merge: client discovery from Gmail        (--no-ff merge commit)
  └─ 16 feature commits 5d51aeb..e08cdfb (squash-readable in `git log 1ef5d41^2`)
e08cdfb fix(discovery): show created-count confirmation, fix utcnow deprecation, add 400-path test
…
5d51aeb feat(discovery): pydantic schemas for client discovery from Gmail
4250a6a spec(client-discovery): scan Gmail to populate clients
10ac069 plan(client-discovery): 13-task TDD plan
```

### Test counts

- Backend: **323 passing** (was 295 — +28 discovery tests)
- Frontend: **247 passing across 45 files** (was 223 — +24 discovery tests)
- `pnpm build` clean; new files lint-clean (5 pre-existing `react-hooks/set-state-in-effect` errors in S2/S3 OAuth-callback + context-brief-toggle files remain — pre-date this work, not in scope)

### Architecture: client discovery at a glance

```
Backend
  POST /api/v1/connectors/gmail/discover-clients
    → ConnectorViewModel.discover_clients
        → GmailClient.fetch_recent_messages   (after:<date>, no domain filter, paged)
        → discovery_aggregator.aggregate()    PURE — freemail/SaaS-noise/own-domain/
                                              no-reply/already-linked filters, ranked,
                                              capped at 30 candidates
  backend/app/services/connectors/discovery_aggregator.py   ← also now owns FREEMAIL_DOMAINS
                                                              (moved here from connector_viewmodel
                                                               to break a circular import)

Frontend
  /clients page (empty-state CTA + secondary button when Gmail connected)
    └─ <ClientDiscoveryFlow>                  state machine: lookback → scanning →
        ├─ <LookbackPicker>                   list → wizard → done | error
        ├─ <CandidateList>                    checkbox bulk-select
        └─ <CandidateReviewWizard>            sequential pre-filled <ClientForm>
  ClientForm gained an inline contacts editor + initialContacts/submitLabel/cancelLabel props
```

### Lessons that ate cycles this session (worth not repeating)

1. **NEVER use `git add -A` in a worktree-based subagent prompt.** A Task-13 subagent ran `git add -A`, which swept up the worktree's `backend/.venv` symlink (created during worktree setup to share the main checkout's venv). The symlink got committed; the `--no-ff` merge then checked it out into the main checkout, **clobbering the real venv directory with a self-referential symlink** (`backend/.venv -> backend/.venv`). Recovery: `git rm --cached backend/.venv`, delete the broken symlink, `uv sync` to rebuild the venv, harden `.gitignore`. **Fix going forward: subagent commit steps must `git add <explicit paths>`, never `-A`.** The plan's per-task commit steps already list explicit paths — the lint-fix follow-up task was the one that improvised `-A`.

2. **`.gitignore` patterns with a trailing slash (`.venv/`, `node_modules/`) match directories ONLY, not symlinks.** That's why the `.venv` symlink slipped past the ignore. Fixed by dropping the trailing slashes (`.venv`, `node_modules`) so symlinks named the same are also ignored. If you ever symlink deps into a worktree again, the gitignore now covers it.

3. **The global axios 401 interceptor (`frontend/src/api/client.ts`) redirects to `/login` on ANY 401.** A connector endpoint returning 401 for "stale Gmail credentials, please reconnect" would log the user out instead of showing the error. `discover_clients` was changed to return **400** for the decrypt/refresh-failure cases (session is fine, only the Gmail credential is stale — 400 is also semantically correct). `sync_emails` still has the latent 401 bug — noted as a follow-up above.

4. **`worktree.baseRef: head`** is set in `.claude/settings.local.json` (added 2026-05-18). EnterWorktree now branches from local HEAD, so worktrees correctly include unpushed spec/plan commits. No more `git merge main --ff-only` dance after worktree creation.

(Earlier lessons still apply: stateful test `Wrapper` for controlled inputs; `vi.spyOn(window,'confirm')` for jsdom; `getByDisplayValue` not `getByText` for input values.)

### Gmail sync needs clients first (product gotcha — not a bug)

`connector_viewmodel.sync_emails` builds its Gmail search query FROM existing client contact domains (`_extract_domains`). An agency with **0 clients** gets `{"new_emails": 0, ...}` in 0 seconds — the Gmail API is never even called. The frontend renders this as a green "Synced 0 new emails" success, which looks like an empty inbox but actually means "no clients to search for." The discovery feature shipped this session is the intended fix — populate clients first, then sync finds their email.

---

## Quick verification (run this first on resume)

```bash
# 1. Repo state
cd /Users/karthikramesh/Developer/nuprop
git log --oneline -3                       # HEAD = 4b62a82
git status                                 # clean, in sync with origin/main

# 2. Local test suites
cd backend && .venv/bin/python -m pytest -q   # → 323 passed
cd ../frontend && pnpm test                    # → 247 passed across 45 files

# 3. Production health
curl -s https://nuprop.fly.dev/api/v1/health   # → {"status":"ok","service":"nuprop"}

# 4. Fly machines
fly machines list -a nuprop                    # 3 expected
```

If `backend/.venv/bin/python` is missing (e.g. fresh clone), rebuild it: `cd backend && uv sync`.

---

## Where to look for what

| Thing | Path |
|---|---|
| **This file** | `docs/superpowers/HANDOFF.md` |
| Client-discovery spec | `docs/superpowers/specs/2026-05-19-client-discovery-from-gmail-design.md` |
| Client-discovery plan | `docs/superpowers/plans/2026-05-19-client-discovery-from-gmail.md` |
| Rate-card wizard spec/plan | `docs/superpowers/specs/2026-05-18-rate-card-form-design.md`, `plans/2026-05-18-rate-card-wizard.md` |
| Project memory (auto-loaded) | `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/` |
| Backend tests | `backend/tests/{unit,integration}/` |
| Frontend tests | `frontend/src/**/__tests__/` |
| Fly config | `fly.toml` (secrets via `fly secrets list -a nuprop`) |
| Auto-deploy workflow | `.github/workflows/deploy.yml` |
| **Client-discovery components (NEW)** | `frontend/src/components/clients/discovery/`, `backend/app/services/connectors/discovery_aggregator.py` |

---

## How to resume next session

1. Read this file end-to-end (~3 min).
2. Run the "Quick verification" block above.
3. Pick from "START HERE":
   - **Smoke tests** (P6 + client discovery + rate-card wizard, ~20 min in browser) → all three are shipped-but-untested.
   - **Rotate secrets** (~10 min in OAuth consoles).
   - **Worktree cleanup** (~1 min).
   - **S5 brainstorm** (start of a ~1.5d backend slice).

Recommended order: smoke → rotation → cleanup → S5.
