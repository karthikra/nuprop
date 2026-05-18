# NUPROP Session Handoff

**Last updated:** 2026-05-18 (rate-card wizard shipped + deployed; P6 smoke test STILL the open S4 gate)
**Latest commit on `main`:** `a975568` (rate-card wizard, 14 commits merged + pushed). Auto-deployed to prod in 1m49s.
**Working tree:** clean. On `main`. In sync with `origin/main`.
**Production:** **LIVE at https://nuprop.fly.dev** — health 200, all 13 secrets deployed, **4-sub-step rate-card wizard live in onboarding step 2** as of `a975568`.

## 🛑 START HERE NEXT SESSION

**Two browser-only smoke tests are pending. Both have been "shipped to prod" without ever being clicked.** Do them in this order:

### 1. S4 P6 — OAuth connector smoke (was pending before today's wizard detour)

Open https://nuprop.fly.dev → register (use `karthik.ramesh@veeville.com` or `@example.com`, NOT `.local` — Pydantic rejects it) → Settings. Walk through these 6 checks in order:

| # | Action | Expected |
|---|---|---|
| 1 | Click **Connect Gmail** | Popup → accounts.google.com → Allow → `/settings/gmail-callback` → "Gmail connected" → closes → parent shows your Gmail address + green Connected badge |
| 2 | Click **Connect Slack** | Popup → slack.com/oauth/v2/authorize → Allow → `/settings/slack-callback` → "Slack connected" → closes → parent shows workspace name |
| 3 | **Drive** card → Sync Now | ~5s → green "Found X documents across Y clients" |
| 4 | **Calendar** card → Sync Now | ~5s → green "Found X meetings across Y clients" |
| 5 | **Gmail** card → Sync Now | ~15s (LLM classifies) → success alert with email/domain counts |
| 6 | **Slack** card → Sync | ~10s → green "Found X mentions across Y clients" |

Debugging: `fly logs -a nuprop | grep -iE "connector|oauth|encrypt" | tail -20`

Common gotchas:
- Popup blocker — allow popups for `nuprop.fly.dev`
- Google `redirect_uri_mismatch` — must be exactly `https://nuprop.fly.dev/settings/gmail-callback` (no trailing slash)
- Slack "Invalid OAuth state" — S1's 10-min nonce TTL elapsed; click Connect again
- Drive/Cal "Google not connected" — do Gmail first

### 2. Rate-card wizard smoke (NEW today — shipped but never tested in browser)

During the same registration flow, you'll be routed to onboarding step 2 BEFORE you reach Settings. Walk through the new 4-sub-step wizard:

| Sub-step | What to verify |
|---|---|
| **2a Offerings** | Click `+ Add offering` → new `O1 · New offering` appears in left rail and is selected. Edit name + code in right pane. Click `+ Add package` → blank row appears in table. Try to set code to a duplicate of another offering's code — it should silently refuse (collision guard from final review) |
| **2b Hourly Rates** | Click a common-role chip (e.g., "Creative Director") → row appears in table with rate input focused, chip disappears. Edit the rate. Click `+ Add custom role` → text input → type → tab to commit |
| **2c Multipliers** | All 4 fixed rows render with defaults (1.5, 0.88, 0.95, 1.5). Mono keys visible (`urgency_rush` etc.). Try setting Rush job to 0 → it'll be dropped from the payload. Click `+ Add custom multiplier` → form appears with amber warning |
| **2d Globals** | 3 fields show defaults (10% / 3 / 2). Primary button label is "Finish rate card →" (not "Save & Continue"). Click Finish → onboarding advances to step 3 (voice calibration) |

Skip behavior: every sub-step's "Skip this section" link advances without filling anything. On 2d, "Skip this section" submits the payload (just like Finish). Verify by skipping all 4 — should land in step 3 with the agency having an empty-ish rate card in the DB.

To inspect what got submitted:
```bash
fly ssh console -a nuprop -C "python -c \"
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    e = create_async_engine(os.environ['DATABASE_URL'])
    async with e.connect() as c:
        r = await c.execute(text('SELECT version, offerings, hourly_rates, multipliers FROM rate_cards ORDER BY created_at DESC LIMIT 1'))
        for row in r: print(row)
asyncio.run(main())
\""
```

## 🔐 After both smoke tests pass — rotate secrets (chat exposure cleanup)

Three secrets were pasted into AI chat transcripts during S4 P4 and need rotation:
- `GOOGLE_CLIENT_SECRET=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`
- `SLACK_CLIENT_SECRET=fdf51ff06cedda29a2f0c27cd1f59415`
- `ENCRYPTION_KEY=t6TjRRsjv8rqhpDf2M-kRFnhw9MGuVx9wBCu5vIYeIk=`

The transcript is local but best practice is to rotate. Full step-by-step instructions are in the conversation history from 2026-05-18 — the short version:

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
5. ⚠️ ENCRYPTION_KEY rotation invalidates ALL stored Gmail + Slack tokens (`connector_viewmodel.py:146,557` both use the vault). After rotation, **disconnect** existing Gmail + Slack in Settings first (avoids decrypt_failed alert), then **reconnect**.
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

All 4 are already merged into main. The branches still exist as references — delete if you want with `git branch -D worktree-m16-m20-s1-backend-hardening` etc.

### S5 — Pipeline integration (~1.5d, all backend)

The biggest semantic slice in the M16-M20 roadmap. Goal: make the proposal pipeline actually CONSUME the context + connector data we've spent S1-S4 setting up.

Open questions to brainstorm:
- Which of the 5 unwired pipeline phases get `context_brief` access first? (analyze_brief, run_research, run_benchmarks, build_cost_model, generate_narrative — only `run_ideation` consumes it today)
- Should `build_cost_model` read `proposal.preferences` directly, or via a normalized lookup in PipelineContext?
- Post-sync email auto-enrichment — trigger via webhook from connector sync, or a separate ARQ job?

Suggested next-session opener: invoke `superpowers:brainstorming` with target "wire context_brief and connector data into the 5 unwired pipeline phases (S5)".

### S6 — Backend polish (~1d, deferrable)

HIGH/MEDIUM cleanups from the M16-M20 audit + retry/backoff. Includes:
- ContextBriefToggle local cache survives invalidation (S2 follow-up)
- `getAuthUrl.isError` / `disconnectSlack.isError` surfacing in connector cards (S3 follow-up)
- Yellow-notice timed strip for the rate-card wizard's soft-required skip (today's deferral — see `docs/superpowers/specs/2026-05-18-rate-card-form-design.md` "Validation" section)

---

## What happened today (2026-05-18)

Two threads:

1. **Started:** continue S4 P6 smoke test + secret rotation (from yesterday's handoff).
2. **Detoured:** user asked to replace the onboarding rate-card JSON-paste with a real form. Full brainstorm → spec → plan → subagent-driven execution → final review → merge + push → auto-deploy. Took the full session.

**P6 smoke + rotation were NOT touched today.** They remain the open S4 gates.

### Today's commits (all on main, all deployed)

```
a975568 fix(rate-card): skip on last step submits; guard against offering code collision
0c1d89c fix(rate-card): derive selectedCode instead of syncing via effect
fe7e6e6 fix(rate-card): remove unnecessary cast in StepRateCard, use RateCardPayload directly
a0901e5 feat(onboarding): rewrite step 2 as a thin RateCardWizard composer
23a64dc feat(rate-card): RateCardWizard composer with payload filtering
14fd11a fix(rate-card): use getByDisplayValue in test, drop redundant sr-only span
01daa80 feat(rate-card): OfferingsStep (2a) — master/detail two-pane with editable code
b5eea06 feat(rate-card): MultipliersStep (2c) — 4 fixed rows + custom with warning
acdb786 feat(rate-card): HourlyRatesStep (2b) — chips + table + custom role
55dbbc0 fix(rate-card): revert GlobalsStep to controlled input, add stateful test wrapper
9bfa8b0 feat(rate-card): GlobalsStep (2d) — 3 fields with help text
e4b0b64 feat(rate-card): WizardShell chrome with progress dots and sticky footer
a7d0fe5 feat(rate-card): add known-multipliers and common-roles constants
b5d40fb feat(rate-card): add key helpers and payload types
c79be97 plan(rate-card): bite-sized TDD plan for onboarding wizard
f305f54 chore: ignore .superpowers/ brainstorming artifacts
046e3aa spec(rate-card): wizard form to replace JSON paste in onboarding step 2
```

### Frontend test count

- 2026-05-17 baseline: 171 passing across 32 files
- 2026-05-18 after rate-card wizard: 223 passing across 41 files (+52 tests)
- `pnpm build` clean; new files have no lint errors (4 pre-existing lint errors in S2/S3 OAuth callback files remain — same `react-hooks/set-state-in-effect` pattern, not in scope)

### Architecture: rate-card wizard at a glance

```
frontend/src/pages/onboarding/step-rate-card.tsx   ← thin composer (~15 LOC, was 107)
  └─ <RateCardWizard onSubmit saving />            ← owns wizard state, payload filtering
        ├─ <WizardShell .../>                       ← chrome: dots + header + body + footer
        │     supports `disabled` and `notice` props
        ├─ <OfferingsStep value onChange />         ← 2a master/detail two-pane
        ├─ <HourlyRatesStep value onChange />       ← 2b chips + table + custom role
        ├─ <MultipliersStep value onChange />       ← 2c 4 fixed rows + custom (warning)
        └─ <GlobalsStep value onChange />           ← 2d 3 fields (markup, options, revisions)

frontend/src/components/rate-card-wizard/
  ├─ known-multipliers.ts   ← single source of truth: 4 magic keys cost_model_builder.py reads
  ├─ common-roles.ts        ← 8 quick-add role chips
  ├─ keys.ts                ← toSnakeKey, nextOfferingCode (pure)
  ├─ types.ts               ← RateCardPayload (extends Record<string, unknown> for parent compat)
  ├─ index.ts               ← barrel export
  └─ __tests__/             ← 50 vitest cases (anchor test guards key drift vs backend)
```

Settings → Rate Card editor (`pages/rate-card/editor.tsx`) is UNTOUCHED — wizard is for first-capture only. Same backend contract (`POST /agencies/me/onboarding` step=2). No backend changes.

### Lessons that ate cycles today (worth not repeating)

1. **`defaultValue + key={value}` is never the right fix for "controlled input doesn't update in test"** — the bug is in the test harness lacking a stateful wrapper. Add `function Wrapper() { const [val, setVal] = useState(...); return <Component value={val} onChange={setVal} /> }` and the spec'd controlled pattern works. Saved this lesson into the plan as ⚠️ — every sub-step task after Task 4 worked first time.
2. **EnterWorktree default baseRef is `fresh` (origin/<default-branch>)** — if local main has unpushed commits and you need them in the worktree, either push first OR set `worktree.baseRef: head` in `.claude/settings.local.json` BEFORE calling EnterWorktree (the setting won't apply mid-call). For today the simpler recovery was `git merge main --ff-only` inside the worktree right after creation.
3. **jsdom doesn't implement `window.confirm`** — any component that calls `confirm()` (OfferingsStep does, for offering delete) needs `beforeEach(() => vi.spyOn(window, 'confirm').mockReturnValue(true))` in the test file or deletion tests will hang.
4. **`getByText` doesn't match input values** — for uncontrolled inputs (`defaultValue=...`), use `getByDisplayValue` instead.

---

## Quick verification (run this first on resume)

```bash
# 1. Repo state
cd /Users/karthikramesh/Developer/nuprop
git log --oneline -3                       # HEAD = a975568
git status                                 # clean, in sync with origin/main

# 2. Local test suites
cd backend && .venv/bin/python -m pytest -q   # → 244 passed (unchanged)
cd ../frontend && pnpm test                    # → 223 passed across 41 files

# 3. Production health
curl -s https://nuprop.fly.dev/api/v1/health   # → {"status":"ok","service":"nuprop"}

# 4. Fly machines
fly machines list -a nuprop                    # 3 expected
```

---

## Where to look for what

| Thing | Path |
|---|---|
| **This file** | `docs/superpowers/HANDOFF.md` |
| Today's spec | `docs/superpowers/specs/2026-05-18-rate-card-form-design.md` |
| Today's plan | `docs/superpowers/plans/2026-05-18-rate-card-wizard.md` |
| Prior specs/plans | `docs/superpowers/{specs,plans}/` |
| Project memory (auto-loaded) | `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/` |
| Backend tests | `backend/tests/{unit,integration}/` |
| Frontend tests | `frontend/src/**/__tests__/` |
| Fly config | `fly.toml` (secrets via `fly secrets list -a nuprop`) |
| Auto-deploy workflow | `.github/workflows/deploy.yml` |
| **Rate-card wizard components (NEW)** | `frontend/src/components/rate-card-wizard/` |

---

## How to resume next session

1. Read this file end-to-end (~3 min).
2. Run the "Quick verification" block above (60 seconds of bash).
3. Pick from "START HERE":
   - **P6 smoke + wizard smoke** (10 min in browser) → catches anything broken since deploy.
   - **Rotate secrets** (10 min in OAuth consoles) → cleanup chat exposure.
   - **Worktree cleanup** (1 min) → tidy `.claude/worktrees/`.
   - **S5 brainstorm** (start of a 1.5d backend slice).

Recommended order: smoke → rotation → cleanup → S5.
