# S9–S13 — Section-Based Proposal Output — Mega-Spec

**Status:** Brainstormed 2026-05-26. Implementation plans pending; this spec describes the full vision, decomposed into five sequential slices (S9 → S13). Each slice is independently shippable.
**Surfaces:** backend (schema migration, two-pass LLM generation, media services, export endpoint, Gmail thread search), frontend (long-form section editor, per-section toolbar, media upload + generation UI, persistent context chip, Gmail thread picker).
**Companion services:** S3 (new bucket `nuprop-proposal-assets`), fal.ai (image / video / TTS — single vendor for all media), NUSTAGE (separate hosting service, not built here; this spec defines the contract NUSTAGE will pull from).

---

## Why

The current proposal output is a flat collection of six text columns (`covering_letter`, `executive_summary`, `scope_sections`, `cost_rationale`, `terms`, `email_draft`) produced by one big `generate_narrative` LLM call. There is no:

- Per-section regeneration (every regen re-runs the whole narrative)
- Media (no images, no video, no audio — text only)
- User-editable structure (the text fields are write-once outputs)
- Section optionality (every proposal has all six fields whether they fit the engagement or not)
- Export contract (the rendered site is a server-baked Astro build; no clean JSON handoff for NUSTAGE to consume)

S9–S13 reshapes the output around **nine canonical proposal sections**, each independently generated, individually editable in a long-form Notion-style editor, and able to carry user-uploaded or AI-generated multimedia. The final proposal is exported as a structured JSON payload that NUSTAGE will pull and render as a shareable HTML site.

## Goals

- A nine-section structured output model that matches how proposals are actually authored and read.
- Two-pass LLM generation that produces independent fact sections in parallel and synthesis sections sequentially on top of them — cheap regen, coherent narrative.
- Per-section editing with auto-save and regeneration (both fresh-variant and prompt-steered).
- Multimedia (image, video, audio) embeddable in every section — uploaded by the user OR generated via fal.ai.
- A clean JSON export contract so NUSTAGE can pull a proposal at any time using a per-proposal share token.
- Fix the long-standing UX bug where dismissing the "paste client context" card removes it permanently with no way to add context later.
- Let the user pull Gmail threads (live-searched) into the same context-paste UI, not just paste raw text.

## Non-goals

- **No "Call to action" or "Appendices" section type.** The user's request lists exactly nine sections; CTA and appendices are out of scope. Future slices may add them.
- **No multi-user collaborative editing, no real-time co-editing.** Single-author per proposal. Auto-save handles solo edits across browser tabs but not concurrent editing.
- **No proposal versioning / history.** Edits overwrite. Snapshots-on-publish are a possible future slice; not in S9–S13.
- **No section reordering.** Order is fixed in the canonical nine-section sequence.
- **No music generation.** Audio is narration-only (text-to-speech of a section's content).
- **No video transcoding beyond an optional first-frame poster.** Upload accepts mp4/mov/webm directly; players render natively in the browser.
- **No proposal-first / chat-first product pivot.** The existing chat-driven pipeline still runs; the editor surfaces AFTER the pipeline produces draft sections.
- **No multi-dimensional rate cards, no `pricing_model` branching, no client-list pagination.** Those are separate design conversations carried over from S6/S8.

## Current state (from codebase exploration)

- `backend/app/infrastructure/db/models/proposal.py:38-44` declares the six text columns the new schema replaces, plus the post-render artifacts `site_url`, `docx_path`, `pdf_path`.
- `backend/app/services/pipeline_service.py::generate_narrative` runs one Bedrock call (Opus 4.7 today) that produces all six output fields in a single structured response.
- `backend/app/services/pipeline_service.py::generate_outputs` builds the Astro site, the DOCX, and the PDF from those six fields and writes the artifact paths.
- `frontend/src/components/chat/context-check.tsx:102` is the "Skip" button that calls `onComplete()` — which the parent treats identically to a successful save, removing the card permanently. That's the bug.
- `backend/app/infrastructure/external/gmail_client.py` has `search_messages` (live, paginated) and `fetch_messages_for_domain`. The picker reuses these without backend changes.
- `backend/app/services/context_service.py` already extracts structured context from raw text — the same pipeline the Gmail picker will feed into.
- No S3 buckets exist in the project today. The AWS account already runs Bedrock in `ap-northeast-1`; the new bucket lives in the same region.
- No fal.ai integration exists in the backend today. The Nano Banana skill at `~/.claude/skills/nano-banana/` is local-only and uses the user's `FAL_KEY`. The backend will need its own `FAL_KEY` secret.

---

## Architecture

### Piece A — The 9-section schema

`Proposal.sections: list[Section] | None` (new JSON column). When NULL, the proposal hasn't reached the section-generation phase yet — pre-S9 proposals stay NULL forever (see Migration).

```python
class SectionType(str, enum.Enum):
    PROBLEM_STATEMENT     = "problem_statement"
    PROPOSED_SOLUTION     = "proposed_solution"
    SCOPE_OF_WORK         = "scope_of_work"
    TIMELINE              = "timeline"
    PRICING               = "pricing"
    QUALIFICATIONS        = "qualifications"
    TERMS_AND_CONDITIONS  = "terms_and_conditions"
    COVER_PAGE            = "cover_page"
    EXECUTIVE_SUMMARY     = "executive_summary"


class Section(TypedDict):
    type: str               # one of SectionType values
    order: int              # 0–8, fixed by canonical sequence
    included: bool          # template default or per-proposal toggle
    content: str            # the LLM-generated and/or user-edited body (markdown)
    assets: list[Asset]     # uploaded + AI-generated media
    metadata: dict          # per-type metadata (e.g. timeline phases, pricing tiers)


class Asset(TypedDict):
    id: str                       # uuid
    kind: str                     # "image" | "video" | "audio"
    s3_key: str                   # nuprop-proposal-assets/{agency}/{proposal}/{asset_id}.{ext}
    url: str                      # presigned URL, 1h TTL, regenerated on read
    caption: str | None
    ai_generated: bool
    prompt: str | None            # generation prompt, if ai_generated
    provider: str | None          # "fal.ai/nano-banana" | "fal.ai/kling-1.6" | "fal.ai/playht" | "upload"
    width: int | None             # image/video
    height: int | None            # image/video
    duration_s: float | None      # video/audio
    poster_s3_key: str | None     # video: first-frame poster image (optional)
```

**Canonical order** (locked, no reordering UI):

| order | type | pass |
|---|---|---|
| 0 | `cover_page` | synthesis |
| 1 | `executive_summary` | synthesis |
| 2 | `problem_statement` | fact |
| 3 | `proposed_solution` | fact |
| 4 | `scope_of_work` | fact |
| 5 | `timeline` | fact |
| 6 | `pricing` | fact |
| 7 | `qualifications` | fact |
| 8 | `terms_and_conditions` | fact |

**Inclusion model:**
- `StrategyTemplate.config` gains a `default_sections: list[str]` field listing which section types are on by default for that template. Existing templates get a backfill that sets all nine on.
- Per-proposal, the user can toggle any section off. The editor shows toggled-off sections greyed-out with a "Re-include" button.
- A section that's toggled off is **not** generated, **not** sent to NUSTAGE, **not** rendered in the editor body.

### Piece B — Two-pass LLM generation

Replaces the current single-call `generate_narrative` phase.

**Pass 1 — Facts (parallel):** Seven independent LLM calls fanned out concurrently. Each gets:
- The brief
- The client context brief
- The cost-model output (only relevant for `pricing` and `scope_of_work`)
- The agency's qualifications data (only relevant for `qualifications`)
- The template's instructions for that section type

Each call returns the section's content (markdown) and metadata (e.g. timeline phases extracted as structured JSON, pricing tiers if multi-tier).

**Pass 2 — Synthesis (sequential):** Two LLM calls, run after Pass 1 completes. Each gets:
- The full Pass-1 output
- The brief and context brief
- Template instructions for that section type

`executive_summary` runs first — it's the only section that needs to read all the facts. `cover_page` runs second — it just needs the agency name, client name, proposal title, date, and a one-line teaser drawn from the executive summary.

Each call uses Claude Sonnet 4.6 (Tier.BALANCED) via Bedrock. Prompt caching reuses the brief + context brief across all calls in the pass for cost reduction. ~10 sections × ~600 output tokens = ~6k total output tokens per proposal; cached input dominates.

**Per-section regeneration:** Two endpoints per section.
- `POST /api/v1/proposals/{id}/sections/{type}/regenerate` — re-runs that section with its original inputs. Fresh LLM call, different output (temperature variance). If the section is a fact, also re-runs `executive_summary` since it consumes the facts (cover_page is too brief to bother).
- `POST /api/v1/proposals/{id}/sections/{type}/refine` — body `{instructions: str}`. Re-runs the section with the user's instructions appended to the system prompt ("Refine this section per the user's instructions. The current content is: …").

**Phase rename:** `generate_narrative` is renamed `generate_sections` and replaced wholesale. `generate_outputs` is renamed `prepare_publish` and only generates the artifact-paths bundle (DOCX, PDF, downloadable HTML) — the live HTML rendering moves to NUSTAGE.

### Piece C — Long-form editor UX

After `generate_sections` completes, the proposal-builder UI transitions out of chat-card mode into a scrollable section-editor surface. The chat history stays visible in a collapsible side panel; the right pane is the editor.

**Section block layout:**

```
┌──── Section header ────────────────────────────────────────┐
│ 03. Problem Statement                              [toggle]│
│ ── inline toolbar ───────────────────────────────────────  │
│  ✏ Edit   ↻ Regenerate   💬 Refine with prompt   📎 Media  │
└────────────────────────────────────────────────────────────┘
[rich-text content area, contenteditable, auto-save 1s debounce]

[asset row: thumbnails of attached media with caption + remove]

[+ Add image] [+ Add video] [+ Add audio]
   ↑ each opens a dropdown: "Upload file" | "Generate with AI"
```

**Edit:** the content area is `contenteditable` Markdown (or a simple ProseMirror-style editor — TBD in S9 implementation). Typing triggers a debounced PATCH to `/api/v1/proposals/{id}/sections/{type}` with `{content: new_markdown}`.

**Regenerate:** posts to `/regenerate` endpoint. Section content replaced atomically; editor re-renders.

**Refine with prompt:** opens an inline text field beneath the section. User types instructions, hits Enter, content replaced. Field stays visible with the prompt for context, until the user moves on.

**Media controls:** each `+ Add <type>` button opens a small menu: "Upload file" (drag-drop / picker) or "Generate with AI" (opens a prompt input). Both write to `sections[].assets[]`.

**Toggle off:** a small icon in the section header toggles `included: false`. The section greys out and shows "Re-include" to bring it back. Toggled-off sections still exist in the DB but aren't sent to NUSTAGE.

**Persistence:**
- Text edits: debounced PATCH (1s after last keystroke). The PATCH body is `{content}` — only the field that changed.
- Asset uploads: immediate write on upload completion.
- Section toggles: immediate write.
- Proposal status stays `editing` until the user clicks **Publish** at the top of the editor. Publish transitions status to `published`, generates the share token, and shows the share URL.

**No "Save" button.** Auto-save is the contract.

### Piece D — Media model

**Storage:**
- New S3 bucket `nuprop-proposal-assets` in `ap-northeast-1` (same region as Bedrock).
- Key shape: `{agency_id}/{proposal_id}/{asset_id}.{ext}` for primary assets. Video posters: `{agency_id}/{proposal_id}/{asset_id}-poster.jpg`.
- Bucket policy: private, no public-read. All access via presigned URLs (1h TTL).
- Bucket lifecycle: assets for unpublished proposals expire 90 days after creation. Published-proposal assets never expire.

**Upload (user files):**
- Frontend POSTs to `POST /api/v1/proposals/{id}/sections/{type}/assets/presign` with `{kind, filename, content_type, size}`.
- Backend validates kind/size/mime against the allowed-types table (image: jpg/png/webp/gif ≤ 10 MB; video: mp4/mov/webm ≤ 200 MB; audio: mp3/wav/m4a ≤ 50 MB), generates a presigned PUT URL, returns `{upload_url, s3_key, asset_id}`.
- Frontend PUTs the file directly to S3 (bypasses Python — no memory pressure on big videos).
- Frontend POSTs to `POST /api/v1/proposals/{id}/sections/{type}/assets/commit` with `{asset_id, caption?}` to record the asset on the section.

**Generation (AI media):** all via fal.ai with a single backend `FAL_KEY` secret.

| Kind | fal.ai endpoint | Approx cost | Approx latency |
|---|---|---|---|
| `image` | `fal-ai/nano-banana` (Gemini 2.5 Flash Image) | ~$0.04 / image | ~5-10s |
| `video` | `fal-ai/kling-video/v1.6/standard/text-to-video` (Kling 1.6, 5s 720p) | ~$0.50 / video | ~60s |
| `audio` (narration TTS) | `fal-ai/playht/tts/v3` or `fal-ai/elevenlabs/tts/turbo-v2.5` | ~$0.01 / 1k chars | ~3-5s |

- Frontend POSTs to `POST /api/v1/proposals/{id}/sections/{type}/assets/generate` with `{kind, prompt}`. For audio narration, `prompt` is replaced by the section's current `content` (the LLM doesn't write it — the user's existing section text is the script).
- Backend calls fal.ai, downloads the result, uploads to S3, records the asset with `ai_generated: true`, `provider: "fal.ai/<model>"`, `prompt`.
- Returns the new asset record. Frontend appends it to the section.

**Service module shape:** one file per kind. `services/media/image_gen.py`, `services/media/video_gen.py`, `services/media/audio_gen.py`. Each exposes `async def generate(prompt: str, **kwargs) -> Asset`. Common helpers (S3 upload, fal.ai client) live in `services/media/_common.py`. Future provider swaps (e.g. swap fal.ai/Kling for Veo) are local to one file.

**Video posters:** when a video is uploaded OR generated, a follow-up background job pulls the first frame via ffmpeg-in-Modal (or fal.ai's `video-to-image` endpoint) and uploads it as `poster_s3_key`. The poster is shown as the thumbnail in the editor and in the NUSTAGE render. **Optional — can defer to S11 if it's slowing the slice down.**

### Piece E — NUSTAGE export contract

`Proposal.share_token: str | None` (new column, ~32 random URL-safe chars). NULL until Publish; set on Publish; never rotated.

**Endpoint:** `GET /api/v1/proposals/{id}/export?token=<share_token>`

- No agency auth required. The token IS the auth.
- 404 if proposal doesn't exist or token doesn't match.
- 404 if proposal status is not `published`.
- Returns the structured payload:

```json
{
  "proposal": {
    "id": "...",
    "project_name": "...",
    "agency": {"name": "...", "logo_url": "https://..."},
    "client": {"name": "...", "industry": "..."},
    "published_at": "2026-05-26T...",
    "sections": [
      {
        "type": "cover_page",
        "order": 0,
        "content": "...markdown...",
        "assets": [{"kind": "image", "url": "https://s3-presigned...", "caption": "...", "width": 1920, "height": 1080}],
        "metadata": {}
      },
      ...
    ]
  }
}
```

Asset URLs are presigned (1h TTL). NUSTAGE caches the payload server-side and refetches when the URL expires.

**Publish action:** `POST /api/v1/proposals/{id}/publish`
- Requires the section to have `status="editing"` and at least one included section with non-empty content.
- Mints `share_token` if not yet set.
- Sets `status="published"`, `published_at=now()`.
- Returns `{share_url}` — the public URL the user copies to send the client (the URL is constructed as `{NUSTAGE_BASE_URL}/p/{proposal_id}?t={share_token}` if NUSTAGE is configured; otherwise the local export URL).
- Idempotent — calling publish on an already-published proposal returns the existing share URL.

**Unpublish:** `POST /api/v1/proposals/{id}/unpublish` transitions back to `editing` and revokes the share token (rotates it; clients with the old URL get a 404). For the rare case of "I sent this too early."

### Piece F — Context UX fixes

**Persistent "Add client context" affordance.**

The current `ContextCheck` component in `frontend/src/components/chat/context-check.tsx` is rendered conditionally based on `hasContext` and a local `mode` state. The fix:

- Lift the "add context" affordance OUT of the chat history and into the proposal-builder layout — a small chip in the right-rail (the sidebar opposite the chat) that always reads "Client context: <status>".
- Status: `none` (no context yet), `loading` (extraction in progress), `populated` (extracted; preview available).
- Clicking the chip opens a modal containing the existing `ContextCheck` UI (paste textarea, Gmail tab — see below, Skip / Extract Context buttons).
- "Skip" closes the modal but leaves the chip visible. No "you've skipped" state — the chip just stays at `none`.
- "Extract" runs the existing extraction path and updates the chip to `populated`.
- After `populated`, clicking the chip opens the modal in "add more" mode — the existing context is shown read-only at the top, paste/Gmail panels below for adding more.

The in-chat `ContextCheck` card from today is removed (no more inline first-message prompt for context). The chip is the always-present surface.

**Gmail thread picker.**

Inside the context modal, alongside the existing paste textarea, a new tab: "Pull from Gmail". Only shown if Gmail is connected (via `useGmailStatus`).

UI:
```
┌─ Pull from Gmail ──────────────────────────────────────────┐
│ Search: [acme.com]                              [Search]   │
│ ───────────────────────────────────────────────────────── │
│ ☐ Re: pricing for Q3 campaign — Priya • 2026-05-22         │
│ ☐ Brand brief feedback — Priya • 2026-05-18 (8 messages)   │
│ ☐ Kickoff meeting notes — Anjali • 2026-05-15              │
│ ───────────────────────────────────────────────────────── │
│ 3 selected   [Use selected]   [Cancel]                     │
└────────────────────────────────────────────────────────────┘
```

- Default search query: `from:<client_domain> OR to:<client_domain>` (derived from `client.contacts[].email`). If the client has no contact emails, the user types a query.
- Live call to `gmail_client.search_messages` (existing). Returns up to 50 threads. ~2s.
- Each row shows subject, top sender, date, and (for multi-message threads) the message count.
- User checks 1–N threads, clicks "Use selected".
- Backend `POST /api/v1/clients/{id}/context/from-gmail` with `{thread_ids: [...]}` — fetches all messages in those threads, joins them as text, runs through `context_service.extract_context_from_text` (the same pipeline `POST /clients/{id}/context` uses today).
- Updates the chip to `populated`.

---

## Migration strategy

**Schema migration `05_proposal_sections_and_share_token`:**

- Add `proposals.sections: JSON nullable`.
- Add `proposals.share_token: VARCHAR(64) nullable, unique`.
- Drop `proposals.covering_letter`.
- Drop `proposals.covering_letter_alt`.
- Drop `proposals.executive_summary`.
- Drop `proposals.scope_sections`.
- Drop `proposals.cost_rationale`.
- Drop `proposals.terms`.
- Drop `proposals.email_draft`.

**Existing-proposal handling:**

Production today has **no real-prod proposals** (per multiple confirmed smoke-test gaps — no agency user has driven a proposal end-to-end). The migration is a clean break: old proposal rows lose their text columns; their new `sections` column stays NULL.

If smoke testing surfaces real proposals before S9 ships, the migration is amended to backfill: each old proposal's six text columns are mapped to a six-element `sections` list (`executive_summary` → executive_summary section, `scope_sections` → scope_of_work section, `cost_rationale` → pricing section, `terms` → terms_and_conditions, etc.). The other three sections (problem_statement, proposed_solution, qualifications, timeline, cover_page) are created with empty content. Backfill runs in the Alembic upgrade.

**Frontend handling of old proposals:**

The proposal-detail view checks `proposal.sections != null`. If null, renders the legacy view (the old six-field display). If non-null, renders the new section editor. Both code paths coexist for one release; the legacy view is removed in a later slice once all old proposals are confirmed migrated or archived.

---

## Slice decomposition (S9 → S13)

Each slice is independently shippable, with its own spec + plan when its turn comes.

### S9 — Sections schema + two-pass LLM generation + minimal editor

**Scope:** Migration adding `sections` + `share_token` columns and dropping the six old text columns. New `rate_gap_analyzer`-style services for the two-pass generation (`SectionFactGenerator`, `SectionSynthesisGenerator`). `PipelineService.generate_sections` replaces `generate_narrative`. New endpoints for per-section PATCH, regenerate, refine. Frontend: long-form scrollable editor with edit + regenerate + refine + toggle-off; NO media yet. Strategy templates gain `default_sections`.

**Estimated:** ~2 weeks. ~25 new tests across backend + frontend.

### S10 — Image: S3 setup + Nano Banana + image upload

**Scope:** Create S3 bucket via Terraform/CloudFormation (or Fly secrets pointing at an existing bucket; decided in S10 spec). Backend `services/media/image_gen.py` wraps fal.ai Nano Banana. `services/media/_common.py` carries the S3 upload helper + presigned URL minting. Asset endpoints (`presign`, `commit`, `generate`, `delete`) scoped per-section. Frontend `+ Add image` button with the upload/generate menu. Asset row in each section. `FAL_KEY` secret added to Fly.

**Estimated:** ~1 week. ~12 new tests.

### S11 — Video + audio narration

**Scope:** Extend the media service module with `video_gen.py` (fal.ai Kling 1.6) and `audio_gen.py` (fal.ai TTS). Endpoints already exist from S10 (`/generate` takes a `kind` param). Frontend `+ Add video` and `+ Add audio` buttons. Audio narration's `prompt` is auto-filled from the section's current `content`. Optional: video first-frame poster generation via a small Modal function or fal's video-to-image.

**Estimated:** ~1 week. ~10 new tests.

### S12 — NUSTAGE export contract + Publish flow

**Scope:** `Publish` button at the top of the editor. `share_token` minting. `POST /api/v1/proposals/{id}/publish` and `/unpublish`. `GET /api/v1/proposals/{id}/export?token=<>` returning the structured payload with presigned asset URLs. `share_url` shown in the editor after publish, with a "Copy" button. NUSTAGE stub: a simple Next.js or Astro app at a sub-path that pulls the JSON and renders a basic shareable HTML — or stay as just the JSON contract and let the real NUSTAGE consume it later (decided at S12 spec time).

**Estimated:** ~3-5 days. ~8 new tests.

### S13 — Context UX: persistent chip + Gmail thread picker

**Scope:** Remove the current in-chat `ContextCheck` card. Add the right-rail "Client context" chip with `none`/`loading`/`populated` states. Modal containing paste textarea + Gmail thread picker. Backend `POST /api/v1/clients/{id}/context/from-gmail` endpoint that fetches threads via `gmail_client.search_messages`, joins messages, calls existing `context_service.extract_context_from_text`. "Skip" no longer dismisses anything — the chip stays.

**Estimated:** ~1 week. ~8 new tests.

**Total:** ~5-6 weeks across five slices. S13 is logically independent of S9-S12 and could ship first as a quick win (it doesn't touch the proposal output model at all).

---

## Cost ceiling per proposal

A rough cost estimate per proposal under the new model, with all 9 sections generated and modest media (1 image, 1 audio narration on the cover):

| Item | Cost |
|---|---|
| 7 Pass-1 fact LLM calls (Sonnet 4.6, ~800 input + ~600 output) | ~$0.03 |
| 2 Pass-2 synthesis LLM calls (Sonnet 4.6, larger input from facts) | ~$0.02 |
| 1 Nano Banana image | ~$0.04 |
| 1 audio narration (~2k chars, fal TTS) | ~$0.02 |
| S3 storage (per-month, ~5 MB per proposal) | <$0.001 |
| **Per-proposal total (baseline media)** | **~$0.11** |

Adding a 5s Kling video pushes it to ~$0.61. Adding regenerations adds ~$0.005 per call. Comfortable headroom against the existing per-proposal pipeline cost (~$2.62 on Opus pre-S9).

---

## Testing approach

- Each section type has at least one fact-generator unit test (mocked LLM) and one synthesis-generator unit test.
- Migration backfill (if added) has its own integration test.
- Media services: each generator unit test stubs fal.ai. Integration tests for upload presign + commit, generate, and delete cover the asset endpoints.
- Editor: vitest tests for the section block component, the per-section toolbar actions, and the media upload/generate menu.
- Export endpoint: round-trip test (publish → fetch with token → verify payload structure).
- Context chip: vitest tests for `none`/`loading`/`populated` transitions, modal open/close, paste flow, Gmail flow.

Per-slice test counts in the slice-specific plans.

---

## Future work

- **Call-to-action and Appendices section types.** Added later; out of scope here.
- **Multi-author / collaborative editing.** CRDT or operational-transform model. Big project.
- **Proposal versioning.** Snapshots on publish; ability to revert.
- **Theme system for NUSTAGE.** Per-agency branding (colors, fonts, logo placement) carried in the export payload.
- **Section templates / snippets.** Reusable section bodies the agency can drop into any proposal ("our standard payment terms").
- **Music gen for proposal background tracks.** Out of scope here; fal.ai supports it via MusicGen if added.
- **Native video transcoding / streaming.** Beyond first-frame poster — full HLS / adaptive bitrate. Out of scope.
- **Real-time generation streaming.** Stream LLM output token-by-token into the editor as it generates, instead of batch-replace on completion. Better UX but requires WebSocket plumbing per section.
