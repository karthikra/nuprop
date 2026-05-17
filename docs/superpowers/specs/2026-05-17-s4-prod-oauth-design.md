# Spec / Checklist — S4: Production OAuth Wiring

**Date:** 2026-05-17
**Slice:** S4 of S0–S6 M16-M20 finish-line
**Depends on:** S3 (connector frontend) merged to main at commit `28694bc`
**Worktree:** `m16-m20-s4-prod-oauth`
**Owner:** Karthik (hands) + AI (guidance)
**Estimate:** 0.5 day (mostly third-party console clicks)
**Status:** active — walk through interactively

---

## Goal

Make the connectors actually work in production. After S1-S3, the backend is hardened, the frontend can drive OAuth flows, and the Slack callback route exists. What's missing is the OAuth app registrations in Google + Slack consoles, and the Fly secrets that wire those credentials into NUPROP.

This slice is different from S1-S3: most of the work is clicking around in third-party UIs. The AI's job is to produce the exact URLs, scopes, redirect URIs, and `fly secrets set` commands; the user's job is to click + paste + confirm.

---

## What "shipped" looks like

After S4, all of the following are true:

1. **Google Cloud OAuth app registered** with Gmail + Drive + Calendar scopes, redirect URI `https://nuprop.fly.dev/settings/gmail-callback`.
2. **Slack OAuth app registered** with the required scopes, redirect URL `https://nuprop.fly.dev/settings/slack-callback`.
3. **7 new Fly secrets set on `nuprop`:**
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://nuprop.fly.dev/settings/gmail-callback`
   - `SLACK_CLIENT_ID`
   - `SLACK_CLIENT_SECRET`
   - `SLACK_REDIRECT_URI=https://nuprop.fly.dev/settings/slack-callback`
   - `ENCRYPTION_KEY` (Fernet key — generated locally via `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`)
4. **App restarts cleanly** — S1's `_validate_connector_secrets` lifecycle check no longer raises (because both client IDs are set AND the encryption key is set).
5. **Manual smoke test passes** at `https://nuprop.fly.dev`:
   - Connect Gmail → popup → consent → redirect back → workspace badge appears.
   - Connect Slack → popup → consent → redirect back → workspace name appears.
   - Sync each connector → success alerts render.

---

## Phase plan

| Phase | What | Who clicks | Estimate |
|---|---|---|---|
| **P1** | Register Google OAuth app in Google Cloud Console | User | ~10 min |
| **P2** | Register Slack OAuth app in Slack API console | User | ~5 min |
| **P3** | Generate ENCRYPTION_KEY locally | AI | 30 sec |
| **P4** | Set all 7 Fly secrets | AI (with user's pasted creds) | 2 min |
| **P5** | Trigger a deploy (auto-deploys on next push, or `fly deploy` manual) | AI | 3 min |
| **P6** | Smoke-test the full OAuth round-trips against prod | User + AI | ~5 min |

---

## Phase 1 — Google Cloud OAuth app

### 1.1 Create / select project

Visit [console.cloud.google.com](https://console.cloud.google.com). If you don't already have a project for NUPROP, create one — name it `nuprop-prod` or similar.

### 1.2 Enable the three APIs

In the cloud console, search for and **enable** these APIs (one click each):

- **Gmail API**
- **Google Drive API**
- **Google Calendar API**

(URL pattern: `https://console.cloud.google.com/apis/library/<api-name>`)

### 1.3 Configure the OAuth consent screen

Navigate to **APIs & Services → OAuth consent screen**.

- **User Type:** External (unless you have Google Workspace)
- **App name:** `NUPROP`
- **User support email:** your email
- **Developer contact:** your email
- **App domain:** leave blank for now (only required for verification)
- **Authorized domains:** `nuprop.fly.dev`

On the **Scopes** step, click "Add or remove scopes" and add these three (search for each):

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/drive.metadata.readonly`
- `https://www.googleapis.com/auth/calendar.readonly`

On the **Test users** step, add your own Google email so you can test before publishing.

Save and continue.

### 1.4 Create OAuth 2.0 credentials

Navigate to **APIs & Services → Credentials → + Create Credentials → OAuth client ID**.

- **Application type:** Web application
- **Name:** `NUPROP Web Client`
- **Authorized JavaScript origins:** `https://nuprop.fly.dev`
- **Authorized redirect URIs:** `https://nuprop.fly.dev/settings/gmail-callback`

Click **Create**. A modal pops up with the **Client ID** and **Client Secret** — copy both. These are the values for `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

⚠️ **The secret is shown only once.** If you lose it you can reset it from the credential's edit screen.

---

## Phase 2 — Slack OAuth app

### 2.1 Create the Slack app

Visit [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.

- **App Name:** `NUPROP`
- **Development Slack Workspace:** your own workspace

Click **Create App**.

### 2.2 Configure OAuth & Permissions

In the left sidebar: **OAuth & Permissions**.

**Redirect URLs:** Add `https://nuprop.fly.dev/settings/slack-callback`. Save.

**User Token Scopes** (scroll down — these are user scopes, NOT bot scopes):

- `search:read`
- `channels:history`
- `channels:read`

(Match the backend's `SlackClient.SCOPES` constant: `"search:read,channels:history,channels:read"`.)

### 2.3 Grab the credentials

In the left sidebar: **Basic Information** → scroll to **App Credentials**.

Copy:
- **Client ID** → `SLACK_CLIENT_ID`
- **Client Secret** (click "Show" to reveal) → `SLACK_CLIENT_SECRET`

---

## Phase 3 — Generate `ENCRYPTION_KEY`

Run locally:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Output is a single 44-character base64 string. That's your `ENCRYPTION_KEY` value.

(Save it somewhere safe — if you lose it, all stored Slack tokens become unrecoverable per S1's `TokenVault.decrypt` fail-loud behaviour. Users would need to re-authorize.)

---

## Phase 4 — Set Fly secrets

Once you have all 5 credentials + the encryption key:

```bash
fly secrets set \
  GOOGLE_CLIENT_ID="<paste>" \
  GOOGLE_CLIENT_SECRET="<paste>" \
  GOOGLE_REDIRECT_URI="https://nuprop.fly.dev/settings/gmail-callback" \
  SLACK_CLIENT_ID="<paste>" \
  SLACK_CLIENT_SECRET="<paste>" \
  SLACK_REDIRECT_URI="https://nuprop.fly.dev/settings/slack-callback" \
  ENCRYPTION_KEY="<paste>" \
  -a nuprop
```

This triggers an automatic rolling redeploy. Wait ~2 minutes.

Verify with:

```bash
fly secrets list -a nuprop
# should show 13 secrets total (6 existing + 7 new)
```

---

## Phase 5 — Verify the deploy

Wait for the rolling redeploy to finish:

```bash
fly status -a nuprop
# Both app machines should show STATE=started, CHECKS=passing
```

Sanity check that the app booted (S1's startup validation now passes):

```bash
curl -sS https://nuprop.fly.dev/api/v1/health
# {"status":"ok","service":"nuprop"}
```

If you see a 502 or the app fails to start, check the logs:

```bash
fly logs -a nuprop | tail -50
# Look for: "Refusing to start: connector credentials are set ..."
# If you see that, ENCRYPTION_KEY wasn't set — re-run fly secrets set.
```

---

## Phase 6 — Smoke test in browser

1. Open `https://nuprop.fly.dev` → log in.
2. Navigate to Settings.
3. **Connect Gmail:** click button → popup opens → consent screen → click Allow → redirect to `/settings/gmail-callback` → popup shows "Gmail connected" then closes → parent page shows your Gmail account + "Connected" badge.
4. **Connect Slack:** click button → popup opens → Slack consent screen → click Allow → redirect to `/settings/slack-callback` → popup shows "Slack connected" then closes → parent page shows the workspace name + "Connected" badge.
5. **Drive:** click Sync Now → wait ~5s → "Found X documents across Y clients" alert.
6. **Calendar:** click Sync Now → wait ~5s → "Found X meetings across Y clients" alert.
7. **Gmail Sync:** click Sync Now → wait ~15s (LLM-classifies each email) → success alert.
8. **Slack Sync:** click Sync Now → wait ~10s → "Found X mentions across Y clients" alert.

If anything fails: `fly logs -a nuprop | grep -i connector` will show the structured event logs from S1.

---

## Open questions / decisions

**Q1 — Publish the Google OAuth app or leave in test mode?**

Recommended: **leave in test mode** for now. Test mode caps total users at 100, which is fine for NUPROP's current state. Publishing requires Google verification (especially for restricted scopes like `gmail.readonly`), which is a multi-week process. Defer until you're past beta.

**Q2 — Use a separate Google project per environment (prod vs dev)?**

Recommended: **yes for the future, no for S4.** For S4 we just need prod to work. When you eventually have a staging environment, add a second OAuth client in the same Google project pointing at the staging redirect URI.

**Q3 — Rotate `JWT_SECRET_KEY` since S1 now uses it for OAuth state signing too?**

Recommended: **no, keep the current value.** It's been in use since deploy, rotating it would invalidate all active user sessions. The OAuth state signing is additive — no security issue from the dual use.

**Q4 — Should we worry about Slack's user-token vs bot-token distinction?**

Recommended: **user-token is correct per the existing backend.** `SlackClient.SCOPES = "search:read,channels:history,channels:read"` are user scopes. The backend's `connector_viewmodel.handle_slack_callback` reads `data.get("access_token")` from the OAuth response, which is the user token in Slack's v2 OAuth response shape. Don't add bot scopes.

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Google OAuth consent screen requires verification before going public | Med — but only blocks publishing | Stay in test mode for S4; add your test users explicitly |
| Slack rejects the redirect URL if it has trailing slash mismatch or http vs https | Low | Use the exact URL: `https://nuprop.fly.dev/settings/slack-callback` (no trailing slash, https) |
| Fly rolling redeploy fails because new app machines can't start with old secrets | Low | Per S1, the lifespan check refuses to boot if connector creds are set without ENCRYPTION_KEY — that's the desired behavior, set them all at once via the multi-secret `fly secrets set` |
| User accidentally pastes credentials into a public chat / terminal scrollback | Med | Recommend `set +o history` in bash before pasting secrets, or use a password manager |
| The popup is blocked by the user's browser | Med | Document in S6 polish; for now the user sees "the popup didn't open" and can disable popup blocker |

---

## What lands next (S5 preview)

After S4: open worktree `m16-m20-s5-pipeline-integration`. The biggest semantic slice — wire context_brief and connector data into 5 unwired pipeline phases (analyze_brief, run_benchmarks, build_cost_model, generate_outputs, run_ideation), make `build_cost_model` consume `proposal.preferences`, and add post-sync email auto-enrichment. Estimated 1.5 days, all backend.
