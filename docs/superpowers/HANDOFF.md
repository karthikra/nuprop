# NUPROP Session Handoff

**Last updated:** 2026-05-22 (S5 pipeline integration shipped + deployed)
**Latest commit on `main`:** `f073dfe` (S5 merge commit). Pushed; auto-deploy run `26272615236` triggered.
**Working tree:** clean. On `main`. In sync with `origin/main`.
**Production:** **LIVE at https://nuprop.fly.dev** — health 200, all 13 secrets deployed. Live features: rate-card wizard (onboarding step 2), Gmail client discovery (`/clients`), and as of this session the proposal pipeline now consumes client context (S5 — backend, not directly visible in the UI).

**M16-M20 roadmap status:** S1–S5 COMPLETE. Only S6 (backend polish, deferrable) remains of the original plan.

---

## 🛑 START HERE NEXT SESSION

The work is shipped; what's pending is **verification + cleanup**, all requiring you in a browser or OAuth console — none of it can be automated. Do it in this order.

### 1. Smoke tests — three features shipped to prod, none ever clicked

Open https://nuprop.fly.dev → register (use `karthik.ramesh@veeville.com` or any `@example.com` — NOT a `.local` email, Pydantic rejects it).

**1a. Rate-card wizard** (onboarding step 2, hit right after registration): walk the 4 sub-steps — Offerings (2a) / Hourly Rates (2b) / Multipliers (2c) / Globals (2d). Every "Skip this section" advances; on 2d "Skip" submits like Finish. Add at least one offering and a couple of hourly rates so later phases have a rate card to work with.

**1b. S4 P6 — OAuth connectors** (Settings page):

| # | Action | Expected |
|---|---|---|
| 1 | **Connect Gmail** | Popup → accounts.google.com → Allow → `/settings/gmail-callback` → "Gmail connected" → green badge + your address |
| 2 | **Connect Slack** | Popup → slack.com/oauth/v2/authorize → Allow → `/settings/slack-callback` → "Slack connected" → workspace name |
| 3 | **Drive** card → Sync Now | ~5s → green "Found X documents across Y clients" |
| 4 | **Calendar** card → Sync Now | ~5s → green "Found X meetings across Y clients" |
| 5 | **Gmail** card → Sync Now | ~15s → success alert. ⚠️ "0 emails" is EXPECTED if you have no clients yet — Gmail sync searches BY client domain (see "Gmail sync needs clients" gotcha below). Step 1c fixes this. |
| 6 | **Slack** card → Sync | ~10s → green "Found X mentions across Y clients" |

**1c. Client discovery from Gmail** (`/clients`, needs Gmail connected):

| Action | Expected |
|---|---|
| `/clients` with 0 clients + Gmail connected | Empty state: "Add a client manually" + "Discover from Gmail" |
| **Discover from Gmail** | Modal "Look back how far?" → 30/90/365 buttons (90 highlighted) |
| Pick a window | "Scanning your inbox…" (~3-20s) → candidate list |
| Candidate list | Checkbox rows: name guess, domain, email count, sender count, date range. Noise filtered (freemail, github/linear/etc., no-reply, your own `veeville.com`) |
| Tick candidates → **Review N selected** | Sequential wizard, pre-filled ClientForm per candidate (name = domain guess, contacts = top senders) |
| After last candidate | "Created N clients" → Done → `/clients` refreshes |

Then re-run **Gmail Sync Now** (step 5) — now that clients exist, it should find real emails instead of "0 emails".

**1d. S5 spot-check (optional, backend behavior).** S5 has no new UI. To eyeball it: create a client, add some context to its profile (the `/clients/:id` context section, or run a connector sync that populates the profile), then create a proposal for that client and run it through. The covering letter / research should reference the relationship. Also: after a Gmail sync, a background `enrich_context_from_emails` ARQ job runs — check `fly logs -a nuprop | grep -iE "enrich"` for `connector.enrich.client_done` events.

Debugging any of the above: `fly logs -a nuprop | grep -iE "connector|oauth|discovery|enrich|encrypt" | tail -30`

Common gotchas: allow popups for `nuprop.fly.dev`; Google `redirect_uri_mismatch` → the redirect URI must be exactly `https://nuprop.fly.dev/settings/gmail-callback`; Slack "Invalid OAuth state" → 10-min nonce expired, click Connect again; Drive/Cal "Google not connected" → do Gmail first.

### 2. Rotate secrets (chat-exposure cleanup) — after smoke tests pass

Three secrets were pasted into AI chat transcripts during S4 and should be rotated:
- `GOOGLE_CLIENT_SECRET=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`
- `SLACK_CLIENT_SECRET=fdf51ff06cedda29a2f0c27cd1f59415`
- `ENCRYPTION_KEY=t6TjRRsjv8rqhpDf2M-kRFnhw9MGuVx9wBCu5vIYeIk=`

Steps:
1. **Google:** https://console.cloud.google.com/apis/credentials → NUPROP Web Client → **Add secret** (don't reset — keep old enabled until the redeploy confirms).
2. **Slack:** https://api.slack.com/apps → NUPROP → Basic Information → App Credentials → **Regenerate**.
3. **Fernet:** `backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`
4. **Atomic push** (ONE command — S1 lifespan refuses to start if OAuth creds are set without ENCRYPTION_KEY):
   ```bash
   fly secrets set -a nuprop \
     GOOGLE_CLIENT_SECRET="<new>" \
     SLACK_CLIENT_SECRET="<new>" \
     ENCRYPTION_KEY="<new fernet>"
   ```
5. ⚠️ Rotating ENCRYPTION_KEY invalidates ALL stored Gmail + Slack tokens (the vault encrypts both). After rotation, **disconnect** then **reconnect** Gmail + Slack in Settings.
6. Disable the old Google client secret once re-auth works.

### 3. Worktree / branch cleanup (~1 min)

Check for leftover worktrees from this session: `git worktree list`. If `s5-pipeline-integration` is still listed, remove it: `git worktree remove --force .claude/worktrees/s5-pipeline-integration` then `git worktree prune`, and `git branch -d worktree-s5-pipeline-integration` (it's merged). (As of this handoff the worktree was already cleaned up — verify.)

### 4. Pick the next slice

- **S6 — backend polish** (~1d, deferrable): ContextBriefToggle cache survives invalidation (S2 follow-up); `getAuthUrl.isError`/`disconnectSlack.isError` surfacing in connector cards (S3 follow-up); rate-card wizard's timed yellow skip-notice; retry/backoff on connector calls.
- **`sync_emails` is fine** — its 401→400 fix already shipped 2026-05-21.
- **`pricing_model`** — S5 carries it in the merged config but `CostModelBuilder` doesn't branch on it (no alternative pricing path exists). If you want it to actually do something, that's a fresh design conversation: *what is the alternative pricing model?*
- Other future-work items are listed in each slice's spec under "Future work".

---

## What happened this session (2026-05-22)

Shipped **S5 — pipeline integration**, the biggest semantic slice of the M16-M20 roadmap: brainstorm → spec → 10-task plan → subagent-driven execution → final review → `--no-ff` merge → push → deploy.

S5 makes the proposal pipeline actually USE the client context that S1-S4 collected. Before S5, of 7 pipeline phases only `run_research` consumed client context; the rest generated proposals as if the agency knew nothing about the client.

### Commits (on main, deployed)

```
f073dfe Merge: S5 pipeline integration            (--no-ff merge commit)
  └─ 12 S5 commits 1df9af9..5251ef9
5251ef9 fix(S5): stamp _sources[email] on context profile after enrichment
eb788c0 feat(S5): sync_emails enqueues enrich_context_from_emails after commit
…
1df9af9 feat(S5): add Proposal.context_brief column
feb2c1f fix(connector): sync_emails returns 400 not 401 for stale Gmail creds   (2026-05-21)
b0c7972 plan(S5)  /  90f75cb spec(S5)
```

### Test counts

- Backend: **339 passing** (was 325 — +14 S5 tests)
- Frontend: 247 passing (unchanged — S5 is backend-only)
- Migration head: `03_proposal_context_brief`

### Architecture: S5 at a glance

```
Three pieces —

A. Context-brief wiring
   New Proposal.context_brief TEXT column (migration 03).
   context_service.get_or_create_proposal_brief(session, proposal):
     returns proposal.context_brief if set; else generates via ContextService,
     persists to the column, commits. First phase pays one LLM call; rest read free.
   PipelineService._load_context_brief delegates to it.
   Wired into: analyze_brief, run_research (pre-existing), run_benchmarks,
     generate_narrative (covering letter), run_ideation.

B. Cost-model preferences
   build_cost_model now calls _merge_preferences_into_config(template_config,
     proposal.preferences) and passes the merged config to CostModelBuilder.
   discount_tags -> cost_model.default_multipliers (CostModelBuilder already
     consumes that). pricing_model is carried but NOT branched on (descope).

C. Post-sync email auto-enrichment
   New ARQ task: app/workers/enrichment.py :: enrich_context_from_emails
     (registered in WorkerSettings.functions).
   sync_emails, after committing email rows, collects clients that got new
     email and enqueues the job. The job feeds EmailIndex rows into
     ContextService.enrich_context_with_emails, writes the merged profile
     back, stamps _sources["email"] (mirrors Drive/Calendar/Slack).
   Terminal job — per-client errors isolated, never fails the sync.
```

### Lessons from this session

- The `backend/.venv` symlink that broke the *client-discovery* merge **did NOT recur** — the `.gitignore` hardening (dropped trailing slash: `.venv`, `node_modules`) correctly ignores symlinks now. Pre-merge verification (`git ls-files | grep .venv` → empty) confirmed it before merging.
- Subagent commit steps used explicit `git add <paths>` throughout — no `git add -A`. See `~/.claude/projects/.../memory/feedback_subagent_git_add.md`.
- Spec-vs-reality drift on `pricing_model`: the first exploration suggested `CostModelBuilder` had a pricing fork to select; the deeper read showed none. The plan header amended the spec's acceptance criterion rather than inventing pricing math. When a plan finds the spec over-promised, amend the plan and flag it — don't silently build the spec's literal words.

### Gotchas worth keeping

- **Gmail sync needs clients first.** `sync_emails` builds its Gmail query from existing client contact domains. An agency with 0 clients gets "0 emails" in 0 seconds — the Gmail API is never called. The client-discovery feature is the intended fix: populate clients, then sync finds their email.
- **Global 401 interceptor.** `frontend/src/api/client.ts` redirects to `/login` on ANY 401. Connector endpoints return **400** (not 401) for stale-Gmail-credential errors so they surface in-app instead of logging the user out. Both `discover_clients` and `sync_emails` already do this.
- **Pipeline phases are separate ARQ jobs** with separate DB sessions — anything shared between phases must be persisted (that's why `context_brief` is a column, not passed in memory).

---

## Quick verification (run first on resume)

```bash
cd /Users/karthikramesh/Developer/nuprop
git log --oneline -3            # HEAD = f073dfe
git status                      # clean, in sync with origin/main
git worktree list               # should be only the main checkout

cd backend && .venv/bin/python -m pytest -q     # → 339 passed
cd ../frontend && pnpm test                      # → 247 passed across 45 files

curl -s https://nuprop.fly.dev/api/v1/health     # → {"status":"ok","service":"nuprop"}
fly machines list -a nuprop                       # 3 machines
```

If `backend/.venv/bin/python` is missing (fresh clone): `cd backend && uv sync`.

---

## Where to look for what

| Thing | Path |
|---|---|
| **This file** | `docs/superpowers/HANDOFF.md` |
| S5 spec / plan | `docs/superpowers/specs/2026-05-21-s5-pipeline-integration-design.md`, `plans/2026-05-21-s5-pipeline-integration.md` |
| Client-discovery spec / plan | `docs/superpowers/specs/2026-05-19-*`, `plans/2026-05-19-*` |
| Rate-card wizard spec / plan | `docs/superpowers/specs/2026-05-18-*`, `plans/2026-05-18-*` |
| Prior specs/plans | `docs/superpowers/{specs,plans}/` |
| Project memory (auto-loaded) | `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/` |
| Pipeline phases | `backend/app/services/pipeline_service.py`, `backend/app/workers/pipeline.py` |
| **S5 new code** | `backend/app/workers/enrichment.py`, `get_or_create_proposal_brief` in `backend/app/services/context_service.py` |
| Backend tests | `backend/tests/{unit,integration}/` |
| Fly config | `fly.toml` (secrets via `fly secrets list -a nuprop`) |
| Auto-deploy workflow | `.github/workflows/deploy.yml` |

---

## How to resume next session

1. Read this file end-to-end (~3 min).
2. Run the "Quick verification" block above.
3. Pick from "START HERE":
   - **Smoke tests** (rate-card wizard + P6 OAuth + client discovery, ~20 min in browser) — three shipped features, none verified.
   - **Rotate secrets** (~10 min in OAuth consoles).
   - **S6 backend polish** — the last roadmap slice (deferrable; fresh brainstorm → spec → plan cycle).

Recommended order: smoke tests → secret rotation → decide on S6.
