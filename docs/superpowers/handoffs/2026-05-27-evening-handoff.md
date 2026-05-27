# NUPROP Session Handoff — 2026-05-27 (Evening)

You're picking up after a long ops session that started with smoke-testing S10 (image media) and snowballed into fixing six pre-existing latent bugs in the pipeline path no one had previously driven end-to-end in prod. Most are now closed; the remaining work is consolidated into one spec the next session will execute against.

**Date written:** 2026-05-27 (end of day). Resume target: morning 2026-05-28.

---

## Read these first, in order

1. **`docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md`** — **THE work definition for tomorrow.** Consolidated list of 15 problems hit today, grouped into 4 sub-slices, with Path B (LLM-routed chat intent) fully designed. ~225 lines. Read end-to-end before starting.
2. **`docs/superpowers/HANDOFF.md`** § "Post-S10 ops (2026-05-27)" — full saga of today's debugging trail (Upstash → Fly Redis migration, Bedrock model swap chain, retry trap, web_search routing). Useful context for WHY the spec recommends what it does.
3. **`docs/superpowers/handoffs/2026-05-27.md`** — this morning's handoff (S9 → S10 transition). Reference only.

Don't re-read the rest of the codebase unless the spec sends you there.

---

## What's locked, what's open

### Locked decisions (don't re-litigate)

- **Bedrock heavy tier stays at Opus 4.6** (`global.anthropic.claude-opus-4-6-v1`) until AWS grants Opus 4.7 access. This account doesn't have 4.7.
- **Research + benchmarks route to direct Anthropic API** (not Bedrock) for the hosted `web_search_20250305` tool. Single-call-site exception to the CLAUDE.md "Bedrock only" policy. See spec § Group A and HANDOFF § 5e.
- **Redis is self-hosted on Fly** (`nuprop-redis` app in `bom`, internal-only). Upstash retired; subscription needs cancellation in a day or two (operator action P7 in spec).
- **Path B (NOT Path A)** for chat intent — LLM-routed classifier, not slash commands. User chose the proper feature over the bandaid.

### Open questions the user must answer before execution starts

The spec ends with these — get them out of the way first thing in the morning:

1. **Path B intent scope** — keep at 6 kinds, or add more (status queries, summaries, etc.)?
2. **Classifier model** — Haiku 4.5 (cheap/fast, ~$0.0002 per classification) or Sonnet 4.6 (more accurate)?
3. **PhaseProgress widget placement** — sticky top-of-chat, floating panel, or sidebar?
4. **Chat-only commands vs. hybrid** — should Path B handle everything, or also add explicit action buttons elsewhere?

5-minute conversation. Don't start coding before these are settled.

---

## Current prod state (verify before you write code)

```bash
fly status -a nuprop
gh run list -w deploy.yml --limit 3
curl -s https://nuprop.fly.dev/api/v1/health
```

Expected at session-end:
- **App** machine `48e71eea0119e8` on **version 42** (skew from today's failed deploy in `bom` capacity shortage; spec P6 covers cleanup)
- **Worker** `865114ce925608` on version 43 (has `ANTHROPIC_API_KEY`)
- **Worker† standby** `865139be669de8` on version 43, started (spec P5 says stop this)
- Latest commit on `main`: **`dfb266f`** (defensive `package_name` None handling) + **`539edae`** (spec doc) on top
- Tests: **467 backend** / 275 frontend, all green
- ARQ Redis points at `nuprop-redis.internal:6379/0` — confirm via `fly secrets list -a nuprop | grep REDIS`

### Smoke-test proposal still in DB

`a55829ea-b28a-4c7c-93d4-d113a240dd7c` — the proposal we've been driving all day. Currently in `cost_model_review` phase with `job_status.state == "failed"` for `build_cost_model` (the `None.package_name[:40]` crash that `dfb266f` fixed). Once `dfb266f` deploys, `POST /chat/{id}/retry` will re-enqueue `build_cost_model` cleanly. Useful for verifying tomorrow's pipeline-reliability sub-slice hasn't broken anything.

---

## Operator prerequisites (already done today, just confirm)

- ✅ S3 bucket `nuprop-proposal-assets` provisioned
- ✅ `FAL_KEY` set in Fly secrets
- ✅ `ANTHROPIC_API_KEY` set in Fly secrets (workspace-scoped, $25/mo cap on the Anthropic console)
- ✅ Redis migrated off Upstash; new self-hosted app deployed
- ⏳ **Cancel Upstash subscription** (spec P7) — wait until ~Saturday to confirm self-hosted Redis is solid, then delete `positive-man-126512` in their dashboard

---

## Recommended execution shape

Same pattern as S10: **subagent-driven development in a per-slice worktree**.

```
EnterWorktree → name: post-s10-stability-and-chat-intent
superpowers:writing-plans → translate the spec into a task-per-deliverable plan
superpowers:subagent-driven-development → execute task-by-task with two-stage reviews
superpowers:finishing-a-development-branch → merge + push when complete
```

The spec has 4 sub-slices in recommended order:

| Sub-slice | Effort | Independent? |
|---|---|---|
| 1. Pipeline reliability (P1, P2, P4) | 1.5 h | yes — ship first as a quick win |
| 2. Path B chat intent (P8) | 4-5 h | yes — biggest piece, do second |
| 3. Visible progress UX (P9, P10) | 3 h | depends on #2's UI patterns |
| 4. Quality + cleanup (P11, P3, ops) | 2 h | last; ties off operator actions and HANDOFF tidy |

Total: **~10-11 h** with reviews. Doable in a focused day, comfortable in two.

Each sub-slice can be its own commit or its own merged branch — your call based on review appetite. The spec doesn't mandate.

---

## Gotchas worth keeping in head

- **ARQ retry trap is fixed only for gate-approval enqueues** (`74568b3`). Worker-chain enqueues in `workers/pipeline.py:78` STILL have the trap — that's spec item **P2**. If something goes wrong with `run_benchmarks` → `build_cost_model` chain during tomorrow's testing, manually delete the `arq:result:<pid>:<phase>` Redis key.
- **Fly worker process auto-stops after `fly secrets set`** — spec item **P1** is the permanent fix. Until then, every secret change needs the manual restart snippet documented in HANDOFF § 5b.
- **Fly `bom` region had CPU capacity issues today** — machine starts/updates can fail with "insufficient CPUs" and need retry. Not a code bug; just retry. Spec item P6 is the leftover version skew from one such failure.
- **`process_stream` is silently dropping citations from Anthropic's hosted web_search responses** — spec item **P4**. The body has good content but `extra_data.citations == []`. Investigation needed: capture an actual response shape (the `benchmarks_findings` row in the DB has one from today) and fix the extraction logic in `research_streaming.py:151+`.
- **CLAUDE.md says "always route through Bedrock; never use ANTHROPIC_API_KEY"** — today's commit at `741afb6` is the documented exception (hosted-tool calls only). Spec item **P3** is the 5-min CLAUDE.md edit to spell out the exception. Until that lands, future-you in a different session may be confused.

---

## Files modified today (for context, not re-reading)

Today's commit chain on `main`: `30d567c` (S10 start) → … → `539edae` (spec doc). Run `git log --oneline a7215dc..HEAD` for the full list. The high-impact commits, grouped:

- **S10 (image media) merge + final fixes**: `68f3c3d`, `51c1fd5`
- **Ops fixes**: `46a89d0`, `7c283d3`, `eb4e2e8`, `d5769ee`, `56758f3`, `eb25043`, `c6d822c`, `741afb6`, `74568b3`, `dfb266f`
- **Redis migration**: `65f5929`, `6e964ff`
- **Docs / spec**: `35b43bc`, `ab78f74`, `85e421d`, `539edae`

Tests at end of session: **467 backend / 275 frontend** all green.

---

## Suggested skills

In order of likely invocation tomorrow:

1. **`superpowers:writing-plans`** — translate the consolidated spec into a per-task plan. Use sub-slice 1 first (smallest, lowest risk) to validate the planning pattern before tackling Path B.
2. **`superpowers:using-git-worktrees`** — single worktree for the whole slice (or one per sub-slice if you prefer independent merges).
3. **`superpowers:subagent-driven-development`** — same pattern as S10 today. Fresh subagent per task, spec-compliance review then code-quality review.
4. **`superpowers:test-driven-development`** — the implementer subagents should follow it for each new helper / endpoint.
5. **`superpowers:requesting-code-review`** — between sub-slices, before merging.
6. **`superpowers:finishing-a-development-branch`** — final merge + push.

If the user wants to start with the smallest win first, sub-slice 1 (P1 + P2 + P4) is ~1.5 h and would feel good as a fast morning warmup before tackling Path B.

---

## What's NOT in scope for tomorrow

- **S11** (video + audio media via fal.ai) — separate roadmap slice
- **S12** (NUSTAGE export + publish + share token) — separate roadmap slice
- **S13** (persistent client-context chip + Gmail thread picker) — separate roadmap slice; the user flagged it at the start of today but it got deferred
- Anything not in `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md`

If the user asks for one of these tomorrow, point them at the spec and confirm they want to swap scope before starting.

---

## TL;DR

Read `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md`. Answer the 4 open questions with the user. Pick sub-slice 1 as the warmup. Execute with subagent-driven-development. By end of tomorrow, all of today's pain is closed AND the chat understands typed phase requests.
