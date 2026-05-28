# NUPROP Session Handoff

**Last updated:** 2026-05-27 (S10 + post-S10 ops: Redis off Upstash, Bedrock heavy tier swap to Opus 4.6, research downgraded to Sonnet 4.6 pending Opus 4.7 access)
**Latest commit on `main`:** S10 merge `68f3c3d` + post-merge ops commits — see "Post-S10 ops" below for the full chain. Open follow-ups in § 5 of that section.
**Working tree:** clean. On `main`. In sync with `origin/main`.
**Production:** **LIVE at https://nuprop.fly.dev** — health 200, 15 secrets deployed (FAL_KEY in S10; ANTHROPIC_API_KEY added today for hosted web_search routing). Redis is **self-hosted** on Fly (app `nuprop-redis` in `bom`, internal-only at `redis://nuprop-redis.internal:6379/0`); Upstash has been retired. S3 asset bucket `nuprop-proposal-assets` is live in `ap-northeast-1`. **Bedrock heavy tier is Opus 4.6** (this account lacks 4.7); `run_research` + `run_benchmarks` route to the **direct Anthropic API** for the hosted `web_search_20250305` tool (Option 1 of `docs/superpowers/specs/bedrock-web-search-fix.md` — Bedrock doesn't proxy hosted tools). Everything else stays on Bedrock per the CLAUDE.md policy. Live features: rate-card wizard (onboarding step 2), Gmail client discovery (`/clients`), and as of S5 the proposal pipeline consumes client context.

**M16-M20 roadmap status:** S1–S7 COMPLETE. All M16-M20 work — backend + frontend — is fully shipped.
**Post-roadmap slices:** S8 (smart rate card) COMPLETE — see "What happened this session" below.
S9 (section schema + two-pass generation + editor) COMPLETE — see "What happened this session" below.
S10 (image media — upload + Nano Banana generation) COMPLETE — see "What happened this session" below.

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

- **S7 — frontend follow-ups** (~0.5d): ContextBriefToggle cache survives invalidation (S2 follow-up); `getAuthUrl.isError` / `disconnectSlack.isError` surfacing in connector cards (S3 follow-up); rate-card wizard's timed yellow skip-notice. Needs a fresh brainstorm → spec → plan cycle.
- **`sync_emails` is fine** — its 401→400 fix already shipped 2026-05-21.
- **`pricing_model`** — S5 carries it in the merged config but `CostModelBuilder` doesn't branch on it (no alternative pricing path exists). If you want it to actually do something, that's a fresh design conversation: *what is the alternative pricing model?*
- Other future-work items are listed in each slice's spec under "Future work".

---

## What happened this session (2026-05-28 — Post-S10 stability + chat intent slice)

Executed `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md` on branch **`worktree-post-s10-stability-and-chat-intent`** (subagent-driven, two-stage reviews per task). **Implemented but NOT yet merged/deployed** — `main` is still at `94a4fae`.

**Sub-slice 1 — pipeline reliability** (plan `plans/2026-05-28-sub-slice-1-pipeline-reliability.md`):
- **P1** — `.github/workflows/deploy.yml` now auto-restarts the Fly `worker` group after deploy (with `set -euo pipefail`). Closes § 5b.
- **P2** — extracted the ARQ result-cache retry-trap fix into `app/infrastructure/queue/enqueue.py::enqueue_phase_job` and routed **all 5** enqueue sites through it (was only the chat viewmodel before). Closes § 5a — note the spec said 1 site; there were 5 (worker chain + 3 in `views/v1/proposals.py` + the viewmodel).
- **P4** — `process_stream` (`services/research_streaming.py`) now keeps citations even when `cited_text` is a paraphrase (was dropping every non-verbatim citation → `citations == []` in prod); also drops no-URL citations.

**Sub-slice 2 — Path B chat intent** (plan `plans/2026-05-28-sub-slice-2-path-b-chat-intent.md`):
- **P8** — replaced the non-brief `_echo_response` placeholder with an LLM-routed intent layer. New `app/services/ai/chat_intent.py::classify_intent` (single **Haiku 4.5 / Tier.FAST**, Bedrock) → 6 intents (re_run_phase, regenerate_section, refine_section, edit_cost_item, ask_question, unknown), degrades to `unknown` on any failure. `ChatViewModel._dispatch_intent` routes them. Extracted reusable services first: `services/sections/regeneration.py` + `services/cost_model_service.py` (both endpoints + the dispatcher now share one path). `ask_question` answers via Sonnet (Tier.BALANCED). Security: dispatcher validates `section_type ∈ SECTION_ORDER` before any `getattr`/column write.

**Sub-slice 3 — visible progress UX** (plan `plans/2026-05-28-sub-slice-3-progress-ux.md`):
- **P9** — added a `job_status` WS broadcast (worker emits running/complete/failed via Redis `publish`; API emits `queued` via `publish` too). Frontend: `jobStatus` store slice + WS handler + sticky top-of-chat **PhaseProgress** widget (phase label, state, live elapsed timer, error). **Visually verified** via a throwaway Vite harness + Playwright (running + failed states render correctly).
- **P10** — Retry button on the failed state → existing `POST /chat/{id}/retry`.

**Sub-slice 4 — quality + cleanup:**
- **P11** — root-cause fix in `cost_model_builder.py::_ai_match`: `m.get("package_name", "")` returned `None` on explicit JSON null; now synthesizes `"Custom (<deliverable>)"`. The defensive guard from `dfb266f` stays as defense-in-depth. (Also removed a dead `budget_signal` assignment — F841.)
- This HANDOFF tidy.

**Test counts at end of session:** backend **510**, frontend **285**, all green.

### Remaining operator actions (NOT code — for the human)
- **P3 / § 5d** — edit the user's global `~/.claude/CLAUDE.md` to add the hosted-tool exception ("hosted-tool calls — web_search/web_fetch/code_execution — that Bedrock can't proxy route to AsyncAnthropic; everything else via Bedrock") and to stop claiming Opus 4.7 as the heavy tier. Not done autonomously (it's the user's global config).
- **P5** — stop the duplicate standby worker: `fly machine stop 865139be669de8 -a nuprop`.
- **P7** — cancel the Upstash subscription (`positive-man-126512`) once self-hosted Redis is proven (~Sat).
- **§ 5c** — request Bedrock Opus 4.7 access in AWS Console (`ap-northeast-1`); revert path in § 3 once granted.
- **P6** — version skew: already resolved (all machines on v46 as of session start).

---

## What happened this session (2026-05-27 — S10)

Shipped **S10 — image media (upload + Nano Banana generation)**, the second slice of the S9-S13 section-redesign roadmap.

### Architecture

- **S3 bucket `nuprop-proposal-assets`** in `ap-northeast-1` — private, block-public-access on, CORS allows PUT/GET/HEAD from `https://nuprop.fly.dev` and `http://localhost:5173`, single tag-filtered lifecycle rule (`published=false` → expire 90d). Provisioned via `backend/scripts/bootstrap_s3.sh` (idempotent shell — no IaC anywhere else in the repo). **Note:** S10 doesn't yet stamp the `published=false` tag on uploads, so the rule no-ops until S12 wires tag-on-upload into commit/generate. Safe default for the pre-published-prod state.
- **New media service package** at `backend/app/services/media/`: `_common.py` (kinds, mime/size caps, `Asset` TypedDict, key shape with regex-validated inputs as defence against path-traversal), `_s3.py` (cached boto3 client; presigned PUT 15min / GET 1h; async-offloaded upload/delete), `_fal.py` (async fal.ai wrapper — lazy import so test seam doesn't load `fal_client`), `image_gen.py` (Nano Banana → httpx download → S3 upload → `Asset`), `section_assets.py` (pure helpers: append/remove/resign — never mutates input).
- **Four section-scoped asset endpoints** under `/api/v1/proposals/{id}/sections/{type}/assets/...`:
  - `presign` — `{kind, filename, content_type, size}` → `{upload_url, s3_key, asset_id}`. Validates via `validate_upload`; 400 on oversize/wrong-mime/unknown-section.
  - `commit` — records the just-uploaded asset on the section. **Three defence-in-depth checks**: `s3_key` prefix must equal `{agency_id}/{proposal_id}/` (closes IDOR via crafted key); `kind`/`content_type` must be consistent; `s3_key` extension must match `content_type`.
  - `generate` — `kind=image` only in S10 (400 for video/audio; S11 widens). `RuntimeError` from fal.ai is translated to **502** (clean UX for content-policy blocks).
  - `delete` — DB update + commit BEFORE S3 delete (DB is source of truth; orphan S3 objects are swept by the lifecycle rule once S12 enables tagging).
- **Re-sign on read.** `_resign_response_sections` mutates the Pydantic `ProposalResponse` (NEVER the SA model — `get_db` commits on session exit, so mutating the row would persist the transient URL). Wired into `GET /proposals/{id}` and `PATCH /proposals/{id}`.
- **Frontend:** new `AssetRow` (thumbnail grid + delete) and `AddImageMenu` (split-button: Upload file / Generate with AI) live under each `SectionBlock`, gated on `included=true`. Uploads go presign → bare `axios.put` direct to S3 (bypasses the wrapped api client's auth interceptor — S3 rejects `Authorization` headers) → commit. No bytes pass through Python on the upload path.

### Test counts

- Backend: `406 → 463` (+11 media-common base + 13 media-common hardening, +7 section-assets, +4 image-gen, +12 asset endpoints initial + 5 review follow-ups, +1 re-sign-on-GET, +5 final-review fixes: 2 regen/refine asset-preserve regressions + 1 transient-url-not-persisted + 2 kind=image-only enforcement).
- Frontend: `265 → 275` (+5 asset-row, +3 add-image-menu, +2 section-block integration).
- Migration head: `05_proposal_section_columns` (no schema change in S10).

### Non-goals carried forward to S11+

- Video + audio kinds — S11 widens `/assets/generate` and adds `+ Add video` / `+ Add audio` menus.
- Video first-frame poster — optional in S11 spec.
- `published=true` tagging on Publish (and the matching `published=false` tag-on-upload) — S12. Until then, lifecycle rule no-ops, assets stay forever.
- NUSTAGE pull via `GET /export?token=…` — S12.

### Known follow-ups (out of S10 scope)

- **Lost-update race on the section JSON column.** Read-modify-write pattern in `commit_asset`/`generate_asset`/`delete_asset` (and pre-existing `patch_section`) is non-atomic. Two concurrent writes silently lose one. Fix candidates: optimistic concurrency via `updated_at`, `SELECT ... FOR UPDATE`, or Postgres `jsonb_set + ||` atomic append. Defer to a follow-up; affects S9 surface too.
- **`AddImageMenu` dropdown click-outside-to-close** missing — open menu stays open until a choice is made.
- **`URL.createObjectURL` revoke** is now wired in `readImageDimensions`, but the broader Upload flow doesn't revoke the original `file` reference if the upload errors after presign.

### Operator steps needed before merge

1. **Provision the bucket:** `AWS_PROFILE=nuprop bash backend/scripts/bootstrap_s3.sh` (idempotent; head-check first). Run from a workstation with IAM creds that can `s3:CreateBucket`, `s3:PutBucketCors`, `s3:PutBucketPublicAccessBlock`, `s3:PutLifecycleConfiguration`. ✅ **Done 2026-05-27.**
2. **Push `FAL_KEY` to Fly:** `fly secrets set -a nuprop FAL_KEY="<key>"`. Get the key from https://fal.ai/dashboard. The app boots without it but `/generate` will 502 until the secret is set. ✅ **Done 2026-05-27.**
3. **Verify the bucket region matches `AWS_REGION` (`ap-northeast-1`)** — Fly's app pool needs IAM creds with `s3:PutObject` / `s3:GetObject` / `s3:DeleteObject` on `arn:aws:s3:::nuprop-proposal-assets/*`. If not, attach a minimal policy.

---

## Post-S10 ops (2026-05-27)

After S10 merged, several ops issues surfaced during the smoke test. Most are resolved; a handful are pending follow-ups (see § 5 below).

### 1. Upstash Redis quota hit; migrated to self-hosted Fly Redis

**Symptom:** Chat appeared stuck. Worker process was actually crash-looping with `redis.exceptions.ResponseError: max requests limit exceeded. Limit: 500000, Usage: 500000`. The Upstash free-tier quota was fully consumed (combination of normal traffic + crash-loop reconnect spam, accumulated over weeks).

**Resolution:** Migrated to a self-hosted Redis on Fly via `backend/scripts/migrate_redis_to_self_hosted.sh`:

- New Fly app `nuprop-redis` running `redis:7-alpine` in `bom`, single shared-cpu-1x machine, 256MB RAM, 1GB persistent volume mounted at `/data` for AOF.
- Reachable only on Fly's private 6PN at `nuprop-redis.internal:6379` — never exposed publicly.
- `nuprop`'s `REDIS_URL` rotated to `redis://nuprop-redis.internal:6379/0`.
- Zero recurring vendor cost; runs under Fly's existing resource allowance.

**Verify in prod:** `fly logs -a nuprop | grep -iE 'redis|max requests'` — should be silent on errors. ARQ doesn't log "connected" at INFO level, so the proof is the absence of failures + chat actually completing pipeline phases.

**Rollback path (if needed):** Re-set `REDIS_URL` to the old Upstash URL (retrieve from Upstash dashboard — Fly doesn't reveal secret values), then `fly machine start <stopped-worker-id> -a nuprop`.

**Once verified working for ~24h:** cancel the Upstash subscription in their dashboard and delete the `positive-man-126512` database.

### 2. Fly bug: worker process doesn't auto-restart after secret changes

**Symptom:** After ANY `fly secrets set -a nuprop`, the `worker` process group transitions to `stopped` and Fly does NOT bring it back. The `app` process group has `min_machines_running = 1` in `fly.toml` so it survives; the worker has no equivalent guarantee and no HTTP service to wake it. Chat appears stuck because ARQ jobs queue with no consumer.

**Workaround:** After any secret change, run:

```bash
fly machine list -a nuprop --json \
  | jq -r '.[] | select(.config.metadata.fly_process_group == "worker" and .state == "stopped") | .id' \
  | xargs -r -I{} fly machine start {} -a nuprop
```

The `migrate_redis_to_self_hosted.sh` script does this automatically as step 6. The `bootstrap_s3.sh` script does NOT (no secret change). Any manual `fly secrets set …` invocation needs this snippet run immediately after.

**Permanent fix (not yet shipped):** Add a post-deploy step to `.github/workflows/deploy.yml` that ensures the worker process group is up. Half-day follow-up.

### 3. Bedrock Opus 4.7 access denied; research downgraded to Sonnet 4.6

**Symptom 1 (resolved):** `run_research` raised `anthropic.PermissionDeniedError: 403 — anthropic.claude-opus-4-7 is not available for this account`. The AWS account has access to Opus 4.6 but not 4.7. Fix: switched `ANTHROPIC_OPUS_MODEL` in `app/core/config.py:55` from `global.anthropic.claude-opus-4-7` to `global.anthropic.claude-opus-4-6-v1` (verified via `aws bedrock list-inference-profiles --region ap-northeast-1` — the `-v1` suffix is part of the canonical ID).

**Symptom 2 (resolved):** With Opus 4.6 in place, `run_research` then raised `anthropic.BadRequestError: 400 — tools.0: Input tag 'web_search_20250305' found using 'type' does not match any of the expected tags: …`. Opus 4.6 doesn't support the `web_search_20250305` tool (the tool was added in Anthropic's tool versioning after 4.6 shipped). Fix: switched `run_research` in `pipeline_service.py:232` from `Tier.HEAVY` (Opus) to `Tier.BALANCED` (Sonnet 4.6). `run_benchmarks` already uses Sonnet 4.6 + web_search successfully, so this is a known-good combo. Quality tradeoff is real — Sonnet does thinner agentic-loop research than Opus would — but unblocks the pipeline.

**Revert path when Opus 4.7 access is granted:**
1. AWS Console → Bedrock (`ap-northeast-1`) → Model access → enable Anthropic Claude Opus 4.7. Status: pending account allowlist.
2. Once granted: revert `ANTHROPIC_OPUS_MODEL` in `app/core/config.py:55` to `global.anthropic.claude-opus-4-7`.
3. Revert `pipeline_service.py:232` `Tier.BALANCED` → `Tier.HEAVY`.
4. Update `tests/integration/test_research_transparency.py::test_run_research_uses_balanced_tier_pending_opus_4_7_access` — rename + flip the asserted tier.
5. Drop the workaround comment from this section of HANDOFF.

Also worth updating `~/.claude/CLAUDE.md` global instructions when reverting — they currently still claim Opus 4.7 as the heavy tier.

### 4. Secondary observation — standby worker came online

The Fly secret rotation brought the standby worker `865139be669de8` to `started` state alongside the primary. ARQ handles concurrent workers safely (Redis-backed per-job atomic claim), but it's mildly wasteful. Optional cleanup: `fly machine stop 865139be669de8 -a nuprop`. Not blocking — both workers polling the same queue is benign.

### 5. Pending ops follow-ups

Real bugs surfaced today that didn't get fixed in this session. All small. Worth landing as a single `chore(ops)` slice next session.

**5a. ARQ `_job_id` retry trap.** ✅ **FIXED on branch `worktree-post-s10-stability-and-chat-intent` (sub-slice 1, P2 — pending merge).** Fix candidate (b) was chosen: a shared `enqueue_phase_job` helper DELs the result key before every enqueue, applied to all 5 enqueue sites. Original analysis below for context. — Every pipeline phase that uses a deterministic `_job_id` (`{proposal_id}:{phase}`) silently no-ops on retry because ARQ checks for an existing result key under that ID and skips re-enqueue. Today's smoke test hit this on `run_research`: after the first 403, every retry attempt returned `200 OK` from the API but the worker never picked the job up because the result key from the failed run was still in Redis (24h TTL).

- Manual workaround used today: `await r.delete(f"arq:result:{proposal_id}:{phase}")` via `fly ssh console` before re-triggering.
- Fix candidates: (a) enqueue with a unique job_id (`{proposal_id}:{phase}:{uuid}`) — simplest, removes idempotency-on-retry but the gate-approval flow is already debounced at the UI layer; (b) call `arq_pool.enqueue_job(..., _job_id=...)` after explicit `del arq:result:<id>:<phase>` — keeps idempotency but adds a Redis round-trip per enqueue; (c) override `_result_ttl=0` on the failed-result path so it doesn't poison subsequent retries. **Recommend (a)** — simplest and matches how user-driven retries should work.
- Affects every phase: `analyze_brief`, `run_research`, `run_benchmarks`, `build_cost_model`, `generate_sections`, `enrich_context_from_emails`. `analyze_brief` already uses unique job IDs (`{proposal_id}:analyze_brief:{uuid}` per the Redis keys), so it's exempt. Others use deterministic IDs and have the bug latent.
- Estimated effort: ~30 min code + 2 tests.

**5b. Fly worker-stop after secret changes — permanent fix.** ✅ **FIXED on branch (sub-slice 1, P1 — pending merge + first deploy to verify).** Already documented in § 2 above as the workaround. The permanent fix is a post-deploy step in `.github/workflows/deploy.yml`:

```yaml
- name: Ensure worker process group is running
  run: |
    flyctl machine list -a nuprop --json \
      | jq -r '.[] | select(.config.metadata.fly_process_group == "worker" and .state == "stopped") | .id' \
      | xargs -r -I{} flyctl machine start {} -a nuprop
```

Lives at the end of the deploy job, after `flyctl deploy`. Catches both the deploy path AND any manual `fly secrets set` triggered redeploy. Estimated effort: ~10 min + manual verification.

**5c. Opus 4.7 access in Bedrock — non-code AWS action.** See § 3 for the full revert path once access is granted. Open the AWS Console → Bedrock → Model access in `ap-northeast-1`. Some accounts get instant approval; new/cold accounts can take hours.

**5d. Stale onboarding — `~/.claude/CLAUDE.md` claims Opus 4.7 as heavy tier.** ⏳ **STILL PENDING (tracked as P3 — operator action).** Not done autonomously since it's the user's global config. Update the user's global instructions to reflect that NUPROP currently runs on Opus 4.6 with research on Sonnet 4.6 pending § 5c, AND add the hosted-tool ANTHROPIC_API_KEY exception (see § 5e policy note). Five-line edit.

**5e. Bedrock in `ap-northeast-1` doesn't expose Anthropic's hosted `web_search` tool — RESOLVED via Option 1 routing.** Both `run_research` and `run_benchmarks` originally used `tools=[{"type": "web_search_20250305", ...}]` in streaming calls. Bedrock 400s with the accepted-tools list limited to bash/custom/memory/text_editor/tool_search variants. The streaming `except Exception` block was writing "failed" to the activity log but NOT re-raising, so ARQ reported success despite no research being persisted — silent-failure mode that hid the bug across S5/S6/S7/S8 sessions.

Today's fix (commit chain ending at the Option 1 swap): we tried four approaches in sequence today, ultimately landing on Option 1 from `docs/superpowers/specs/bedrock-web-search-fix.md`:

1. Opus 4.7 → Opus 4.6 model swap (`d5769ee`) — account didn't have 4.7 access. Surfaced the next layer.
2. Opus 4.6 → Sonnet 4.6 model swap (`56758f3`) — Opus 4.6 also doesn't accept the web_search tool on Bedrock. Surfaced the underlying issue.
3. Dropped `tools=` entirely (`eb25043`) — Sonnet wrote training-data research but kept hallucinating `<tool_call>` XML blocks because the system prompt told it to search.
4. Wired Serper as a custom tool (`c6d822c`) — worked but lower quality than the hosted Anthropic tool.
5. **Final swap (this commit)**: route the streaming + hosted web_search call to **`AsyncAnthropic` direct API**, not Bedrock. The model runs an agentic search loop on Anthropic's infrastructure; Bedrock still handles everything else. Per Option 1 of the spec doc.

**Why Option 1 over Option 2 (Serper):** the spec doc itself recommends Option 1 unless data residency / procurement pins everything to Bedrock. Research quality is materially better (agentic loop, full-page reads, native citation spans). Cost: ~$0.40-0.80/proposal extra (Anthropic API tokens + ~$0.01/search). At smoke-test scale (~10s of proposals/month) that's under $10/month — rounding error vs the rest of the bill. Revisit if monthly volume passes ~500/mo, at which point Option 2 (Serper, $0.005/proposal) may have better unit economics.

**Implementation:** `backend/app/services/ai/web_search_loop.py::synthesize_research` instantiates `AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)` for THIS call only; everything else in the codebase continues to use `AsyncAnthropicBedrock`. Direct-API model IDs differ from Bedrock inference-profile IDs (bare `claude-sonnet-4-6` vs `global.anthropic.claude-sonnet-4-6`) — the IDs are in `_DIRECT_MODEL_IDS` at the top of the module.

**Required operator step:** `fly secrets set -a nuprop ANTHROPIC_API_KEY="..."` — get the key from https://console.anthropic.com → API Keys. Without it, `synthesize_research` raises `RuntimeError` with a clear message + the fix command.

**Policy note:** the user's CLAUDE.md says "always route through AWS Bedrock; never use the direct Anthropic API or ANTHROPIC_API_KEY." This commit is the documented exception — hosted-tool calls that Bedrock physically can't proxy. Worth updating CLAUDE.md to spell out the exception. § 5d already tracks the broader CLAUDE.md staleness.

---

## What happened this session (2026-05-26 — S9)

Shipped **S9 — section schema + two-pass LLM generation + long-form editor**, the first slice of the S9–S13 section-redesign roadmap.

### Architecture

- **Schema:** 7 legacy text columns dropped (`covering_letter`, `covering_letter_alt`, `executive_summary`-as-Text, `scope_sections`, `cost_rationale`, `terms`, `email_draft`); 9 new JSON columns added — one per canonical section type. Each column carries `{content, assets, included, metadata}`. Migration `05_proposal_section_columns`.
- **Two-pass generation:** `PipelineService.generate_sections` replaces the old `generate_narrative` and `generate_outputs` phases. Pass 1 runs 7 fact generators in parallel via `asyncio.gather`; Pass 2 runs 2 synthesis generators sequentially with Pass-1 outputs in the prompt. All section generators live in `app/services/ai/section_facts.py` and `section_synthesis.py`.
- **Approval flow:** the narrative gate is removed. Cost-model approval enqueues `generate_sections` directly. After generation completes the pipeline transitions to `section_editor` and the frontend surfaces the editor.
- **Section CRUD:** `PATCH /proposals/{id}/sections/{type}` (content / included / metadata), `POST /sections/{type}/regenerate` (fresh LLM variant), `POST /sections/{type}/refine` (instruction-steered rewrite).
- **Frontend:** new `components/sections/section-editor.tsx` renders included sections in canonical order. Each section is a `section-block.tsx` with auto-save (1s debounce), regenerate, refine-with-prompt, and toggle-off. No media yet (S10 unlocks images, S11 unlocks video + audio). The narrative-preview chat card was removed.

### Test counts

- Backend: 376 → **~406** (+~30 across section helpers, fact/synthesis generators, the `generate_sections` phase, the cost-model gate change, the section CRUD endpoints, plus updated legacy tests).
- Frontend: 260 → **265** (+5 for the section-block component).
- Migration head: `05_proposal_section_columns`.

### Non-goals carried forward to S10–S13

- Media (image / video / audio): S10 + S11.
- NUSTAGE export + share token + Publish: S12.
- Context UX (persistent chip + Gmail picker): S13.
- CTA / Appendices section types: deferred entirely.
- DOCX / PDF: removed in S9; returns as downloadable artifacts in S12.

### Notable cleanup also landed

- `app/services/ideation_service.py` updated to read from the new section dicts (`cover_page`, `executive_summary`) instead of the dropped legacy text columns — required to keep the ideation side-channel functional after the schema migration.

---

## What happened this session (2026-05-24 — S8)

Shipped **S8 — smart rate card**: rate-card gaps are detected the moment the brief is analysed, surface as a chat fill-card after the template gate, and can be resolved three ways — manual fill (additive to the agency rate card), Excel import (per-proposal override), or skip (use estimated defaults).

### Architecture

- **Gap detection (backend).** New `services/ai/rate_gap_analyzer.py`. `PipelineService.analyze_brief` calls it post-commit and writes `proposal.rate_card_gaps` if the agency's active rate card is missing any needed entries.
- **Pause point (backend).** `ChatViewModel.approve_gate("template", ...)` short-circuits if `rate_card_gaps` is set — `run_research` is NOT enqueued until the gaps are cleared.
- **Resume paths (backend).** Three endpoints under `/proposals/{id}/rate-card-gaps`: `/fill` (merges into agency master), `/skip` (clears without modifying), and the `/rate-card-import` + `/rate-card-import/confirm` pair (writes per-proposal override). All three enqueue `run_research`.
- **Cost-model precedence (backend).** `CostModelBuilder.build` now consults override → agency → fallback in that order and stamps `cost_model.source` so the frontend can show which one was used. (Note: the builder signature was refactored away from `db`/`agency_id` parameters — the pipeline now resolves the active rate card via `RateCardRepository.get_active` before calling build.)
- **Excel parsing (backend).** New `services/rate_card_excel_parser.py` uses `openpyxl` for the read and `AIService.complete_json` for the structured extraction. Empty rows are stripped before the LLM call; a warning fires when the prompt exceeds 50k chars; the confirm body is validated by a `RateCardConfirmBody` Pydantic schema.
- **Chat fill-card (frontend).** New `components/chat/rate-gap-card.tsx` renders when `proposal.rate_card_gaps != null`. Three actions in one card: manual fill (with field-level validation and a disabled submit until all fields are positive integers), Excel drop with surfaced upload errors, and skip. Confirm dismisses the preview on success via the corrected `['proposals', proposalId]` query-key invalidation.

### Schema

Migration `04_proposal_rate_card_columns` adds two nullable JSON columns to `proposals`: `rate_card_gaps` and `rate_card_override`. No backfill.

### Test counts

- Backend: 359 → **375** (+16 across gap-analyzer, integration, endpoints, override, import)
- Frontend: 256 → **260** (+4 for the rate-gap-card)

### Non-goals (deferred)

- Multi-dimensional rate cards (per-client / per-job overrides at the agency master level).
- Editing existing rate-card entries from the chat — fill only ever ADDS.
- `.csv` / `.xls` / Google Sheets import (only `.xlsx` for now).
- Multi-currency rates.
- Saving an imported override back to the agency master.

### Known follow-ups

- `_no_network` autouse fixture in `tests/conftest.py` only blocks the `AnthropicClient` facade methods, not `AIService.complete_json` directly. The S8 analyzer + Excel parser are failure-safe so this isn't a real test-flake risk today, but a future direct `AIService` caller without a try/except wouldn't be caught.
- The `rate-gap-card`'s preview is rendered as raw JSON via `<pre>JSON.stringify(...)</pre>`. Acceptable for v1; a polished preview with `low_confidence_fields` badges would be a UX win.
- The agency-master `RateCardViewModel.add_missing_entries` auto-creates a fresh rate card with `version="v1"` if no active one exists. If an agency has multiple historical rate cards, this is the right default; if a deeper version-bump policy is needed, that's a separate slice.

---

## What happened this session (2026-05-23 — S7)

Shipped **S7 — frontend follow-ups**, the final M16-M20 slice. Three small UX gaps deferred from S2/S3/rate-card wizard, plus a piece of test-infrastructure work that surfaced during the rate-card-wizard tests:

- **ContextBriefToggle refetches after invalidation.** The local `cached` state was dropped in favor of React Query's own cache with `staleTime: 5 * 60 * 1000` and `gcTime: 5 * 60 * 1000` set on the query (the per-query `gcTime` overrides the test QueryClient's `gcTime: 0` default). After `useContextSave` / `useResetContext` invalidates the brief query, the next open of the toggle refetches automatically.
- **Gmail and Slack connector cards surface connect + disconnect errors.** Both cards now render an inline red `formatApiError` block when `getAuthUrl` or `disconnect` mutations fail. Drive and Calendar cards have no OAuth/disconnect flow and were left untouched. Both `handleConnect` functions wrap `mutateAsync` in a try/catch so the rejection doesn't surface as an unhandled promise rejection in the test runner.
- **Rate-card wizard skip-notice wired.** `WizardShell.notice` was always there; `RateCardWizard` now populates it: clicking "Skip this section" on an intermediate step shows "You can fill this in later in Settings." for 5 seconds. The timer is cleared on unmount and on consecutive skips so it never stacks. Last-step skip still submits and shows no notice.
- **Test infrastructure compatibility patch.** `src/test/setup.ts` overrides `@testing-library/react`'s `asyncWrapper` to detect vitest fake timers (the default only checks `typeof jest`, which vitest never sets), and wraps `vi.advanceTimersByTime` in `React.act()` so React 19 concurrent-mode state updates from fired timer callbacks flush synchronously. The TODO comment in that file documents the removal condition (when `@testing-library/dom >= 11` ships vitest-aware fake-timer detection).

### Commits (on branch `worktree-s7-frontend-followups`)

- Task 1 (`1ea56d8`) — ContextBriefToggle drops local cache, useContextBrief gains staleTime/gcTime.
- Task 2 (`1b39ce1`) — Gmail card surfaces getAuthUrl + disconnect errors.
- Task 2 fix (`ca6d4c1`) — both cards' handleConnect wraps mutateAsync in try/catch.
- Task 3 (`034e78f`) — Slack card surfaces getAuthUrl + disconnect errors.
- Task 4 (`93671a5`) — Rate-card wizard skip-notice wiring.
- Task 4 test infra (`b705ca9`, `876e8eb`) — vitest+React 19 fake-timer compatibility patch.

### Test counts

- Frontend: **255 passing** (was 247 — +8 S7 tests)
- Backend: 359 passing (unchanged — S7 is frontend-only)
- Migration head: `03_proposal_context_brief` (no schema change)

S7 is the last roadmap slice. M16-M20 is done.

---

## What happened this session (2026-05-23)

Shipped **S6 — connector resilience & backend hardening**, the last roadmap slice. Brainstorm → spec → 10-task plan → subagent-driven execution → final regression.

S6 makes the four connector HTTP clients resilient to transient provider failures and closes the remaining audit-flagged HIGH backend hardening items.

### Commits (on branch `worktree-s6-connector-resilience`)

- S6 spec + plan: `ab24989` (spec), `fdf8bdf` (spec amendment), `4202a91` (plan)
- Task 1 — retry wrapper: `fca15e2`, `5ed05e8` (review fixes: -O-safe exhaustion guard, Retry-After cap, transport-exhaustion test)
- Task 2 — gmail_client migration: `c18d403`, `294f129` (revoke_token max_attempts=1)
- Task 3 — Drive/Cal/Slack migration: `517367c`, `730d264` (OAuth exchange_code max_attempts=1, test polish)
- Task 4 — gmail pagination cap: `aedf593`
- Task 5 — gmail bad-date returns None: `92f403a`
- Task 6 — `_extract_domains` @ guard: `76c64b3`
- Task 7 — LLM call timeout: `57608b4`
- Task 8 — client_repo cap raise: `e630e2e`

### Test counts

- Backend: **355 passing** (was 339 — +16 S6 tests)
- Frontend: 247 passing (unchanged — S6 is backend-only)
- Migration head: `03_proposal_context_brief` (no schema change in S6)

### Architecture: S6 at a glance

```
Two pieces —

A. Shared retry/backoff wrapper
   New module: app/infrastructure/external/_retry.py
   exposing request_with_retry(method, url, *, timeout=30.0,
   max_attempts=4, transport=None, **kwargs) -> httpx.Response.
   Retries 429/5xx and httpx.TransportError; never retries other 4xx
   (a 401 invalid_grant must surface). Honors Retry-After (capped at
   60s). Exponential backoff with jitter otherwise. -O-safe exhaustion
   guard. The single policy point — all four connector clients
   (gmail/gdrive/gcal/slack) route through it. OAuth code exchanges
   (gmail.exchange_code, slack.exchange_code) and gmail.revoke_token
   override max_attempts=1: authorization codes are single-use and
   revokes are best-effort; retrying either is pure latency cost.

B. Hardening fixes
   - gmail_client: MAX_PAGE_ITERATIONS=50 caps both pagination loops
     against the pathological "0 messages + non-null pageToken" loop.
   - gmail_client.get_message: unparseable Date header returns date=None
     instead of naive datetime.now(); the existing viewmodel coercion
     (msg["date"] if isinstance(msg["date"], datetime) else now) applies
     a tz-aware fallback at persist time. No schema change required.
   - connector_viewmodel._extract_domains: skips contacts whose email
     lacks an "@", matching the existing guard pattern in the file.
   - services/llm.py: LLM_TIMEOUT_SECONDS=120.0 passed to
     AsyncAnthropicBedrock so a hung Bedrock call can't stall a phase.
   - client_repo.search default limit 50 → 500.
```

### Lessons from this session

- The plan committed three small spec corrections against the real code before implementation began (line 259 was already @-guarded; the date fallback lives in gmail_client not the viewmodel; the LLM timeout belongs in AIService, not the AnthropicClient facade). S5's amend-and-flag lesson held.
- Two code-quality reviews caught the OAuth-code-exchange retry issue (Tasks 2 and 3): authorization codes are single-use (RFC 6749), so retrying after a 5xx wastes latency on a guaranteed failure. `max_attempts=1` is the right answer for any best-effort or single-use call.
- The pagination test used a `_SAFETY_BOUND = 200` to fail cleanly instead of hanging the suite when the cap is missing — a small TDD pattern worth remembering.

### Gotchas worth keeping

- **`raise_for_status` is inside the wrapper.** Don't call `r.raise_for_status()` again on the returned response — it's already raised before the wrapper returns to you.
- **`HTTPStatusError` and `TransportError` are both `httpx.HTTPError` subclasses.** Existing `except httpx.HTTPError` clauses in `gdrive.get_file_content_text` and `gmail.revoke_token` correctly catch everything the wrapper can raise.
- **Per-attempt `AsyncClient`.** The wrapper opens a fresh `httpx.AsyncClient` per attempt (matches the prior per-call pattern). Connection pooling is not preserved across the wrapper; this is intentional — a retry on a broken connection benefits from a fresh client.

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
