# S8 — Smart Rate Card — Design

**Status:** Brainstormed 2026-05-23. Implementation plan: pending.
**Surfaces:** backend + frontend. Schema migration (one column on `proposals`, plus a second already-planned column). No new tables.
**Slice:** S8. Standalone — not a follow-on to S6/S7 in any technical sense; just the next priority after the S6/S7 hardening landed and the smoke test surfaced this gap.

---

## Goal

Today, when an agency starts a proposal but hasn't fully filled out the rate-card wizard at onboarding, the cost-model phase silently falls back to `_fallback_model(brief)` (`backend/app/services/ai/cost_model_builder.py:96`). The proposal still completes, but with made-up pricing. The agency only notices when they read the output, by which point three other pipeline phases have already burned LLM credits on incomplete context.

S8 flips this from a silent fallback to an explicit, just-in-time fill-checkpoint:

1. **Detect** what rates and offerings this specific proposal will actually need, the moment the brief is analysed.
2. **Surface** the gap as a chat fill-card right after `analyze_brief`, before research is enqueued.
3. **Let the user fill** the gap in any of three ways: drag in an Excel spreadsheet, type values manually, or skip and accept the fallback pricing.
4. **Use the filled data** for THIS proposal — without forcing it onto the agency's master rate card unless the user wants it there.

The net effect: rate cards grow organically per proposal, the user is never blocked by an empty rate card at onboarding, and the cost model always knows whether it's working with real rates or estimates.

## Non-goals

- **Multi-dimensional rate cards** (per-client or per-designer-per-job override matrices). S8 stores at most one override per proposal. The richer rate-card model is a separate future slice.
- **Editing existing rate-card entries from the chat.** S8 only fills gaps and accepts imports — modifications to entries already in the agency rate card stay in the Settings rate-card editor.
- **Re-running the gap check** if the brief changes after the first commit. Detection runs once, after the first `analyze_brief` succeeds.
- **Excel formats other than `.xlsx`.** No `.xls`, no `.csv`, no Google Sheets import. One format keeps the parsing surface narrow.
- **Multi-currency rates.** If the spreadsheet has a Currency column, we surface a preview warning but assume the values are INR (matching the rest of NUPROP).
- **Saving the imported Excel as the agency master.** The override stays per-proposal. A "Save to agency rate card" toggle could be a tiny follow-up; out of scope for S8.
- **Rolling the agency-master gap-fill back into the master rate card automatically.** Today the existing manual gap-fill path in the spec DOES extend the agency rate card with new entries (additive, no overwrites). The Excel path does NOT. The two paths have different semantics and that's intentional.

## Current state (from codebase exploration)

- `backend/app/services/ai/cost_model_builder.py:96` returns `_fallback_model(brief)` when the rate-card row is empty or missing. No surface signal — the proposal just gets fallback pricing.
- `backend/app/services/ai/cost_model_builder.py:99-100` reads the rate card as `{offerings, hourly_rates}` and feeds it to `_ai_match` along with the brief's deliverables.
- `backend/app/services/pipeline_service.py` already implements the phase-chaining (each phase enqueues the next via `_NEXT_PHASE`). Pausing the chain just means: do not enqueue the next phase, return.
- `backend/app/infrastructure/db/models/proposal.py` exposes `status: str` (`draft|generating|review|sent|...`), `pipeline_state: JSON`, and the per-phase output columns. No existing column captures "awaiting rate-card fill" or "uses an override rate card".
- `frontend/src/components/chat/` has the per-phase card pattern in place: `cost-model-card.tsx`, `approval-gate.tsx`, `preference-panel.tsx`. The chat container renders the active card based on proposal state. The fill-card we'll build slots into this surface.
- `backend/app/services/llm.py` exposes `AIService.complete_json(prompt, ...) -> Any` via `AsyncAnthropicBedrock`. That's the call we use both for gap analysis and for Excel structured extraction.
- Migration head: `03_proposal_context_brief`. S8 adds `04_proposal_rate_card_columns`.

## Architecture

### Piece A — Gap detection

A new file: `backend/app/services/ai/rate_gap_analyzer.py`. One public coroutine:

```python
async def analyze_gaps(brief: dict) -> dict:
    """Given a brief, return the roles and offering categories the cost model
    will need. Pure inference — does NOT diff against any rate card.

    Returns: {"needed_roles": [str], "needed_offerings": [str]}
    """
```

Single LLM call (Sonnet 4.6, ~500 token cap). Prompt: given the brief's deliverables/scope, what hourly roles (e.g. `senior_strategist`, `junior_designer`) and offering categories (e.g. `annual_retainer`, `brand_identity`) would the agency need from a rate card to price this? Return strict JSON arrays.

`PipelineService.analyze_brief` is extended: after the brief is analysed and committed, the service calls `analyze_gaps(brief)`, fetches the agency's active `RateCard` via the rate-card viewmodel, and diffs:

- `missing_roles = needed_roles - set(rate_card.hourly_rates.keys())`
- `missing_offerings = needed_offerings - set(rate_card.offerings.keys())`

If both lists are empty → enqueue `run_research` as today.
If either is non-empty → write `proposal.rate_card_gaps = {missing_roles, missing_offerings, needed_roles, needed_offerings}` and DO NOT enqueue the next phase. The pipeline is paused. (`needed_*` is kept alongside `missing_*` because the frontend needs the full list to render context — "these roles will be priced; you have 3 of 5".)

The pause is signalled to the frontend by the proposal payload: when `rate_card_gaps` is non-null, the chat shows the fill-card. Status stays `generating` — no new enum value needed.

### Piece B — Manual fill path

`POST /api/v1/proposals/{id}/rate-card-gaps/fill` accepts:

```json
{
  "hourly_rates": { "senior_strategist": 4500, "junior_designer": 1800 },
  "offerings": { "annual_retainer": { "name": "Annual Campaign Retainer", "base_price": 1500000 } }
}
```

Behavior:

1. Validate the submitted keys against the proposal's stored `rate_card_gaps.missing_*` (caller can't sneak in unrelated entries that would silently mutate the agency rate card).
2. Patch the agency's active `RateCard`: merge new entries into `hourly_rates` and `offerings`. Existing entries are never overwritten (this is the agency's master, not the per-proposal override).
3. Clear `proposal.rate_card_gaps`, enqueue `run_research` to resume the pipeline.

`POST /api/v1/proposals/{id}/rate-card-gaps/skip` clears the gaps without modifying any rate card and enqueues `run_research`. Cost-model phase will hit `_fallback_model` for the missing entries — same as today's silent path, but now explicit.

### Piece C — Excel import path

New endpoints scoped to one proposal:

- `POST /api/v1/proposals/{id}/rate-card-import` — multipart upload, single `.xlsx` file, max 5 MB. Body field name: `file`. Reads the workbook with `openpyxl`, serialises the first sheet (or each sheet if there are several — read all, label by name) to a JSON-of-rows: `[{cells: [{type: "str|num|formula", value: ...}]}, ...]`. Then calls `AIService.complete_json` with a strict prompt: "Extract a rate card from this spreadsheet. Schema: `{hourly_rates: {role_key: rate_inr}, offerings: {offering_key: {name, base_price, packages?}}, multipliers?: {key: percent}}`. Leave fields you can't identify confident enough about as null and list them in `low_confidence_fields`." Returns the parsed structure to the frontend as a preview — NOT yet stored on the proposal.

- `POST /api/v1/proposals/{id}/rate-card-import/confirm` accepts the (possibly user-edited) preview structure and writes it to `proposal.rate_card_override`. Clears `proposal.rate_card_gaps`, enqueues `run_research`.

The two-step (upload-then-confirm) is important because Excel parsing is fuzzy. The user must see what the LLM extracted and have a chance to correct low-confidence rows before the proposal commits to those numbers.

The drag-and-drop area lives **inside** the gap-fill chat card, alongside the manual fill form. Dropping a file replaces the manual-form view with a "parsed preview" view; the user confirms (which calls `/confirm`) or cancels back to the manual form.

The Excel path does NOT touch the agency master rate card. It writes only to `proposal.rate_card_override`, which is consulted by the cost model for this proposal only.

### Piece D — Cost model consults the override first

`CostModelBuilder.build` (`backend/app/services/ai/cost_model_builder.py:78` area) is changed so the rate-card source is resolved with this precedence:

1. `proposal.rate_card_override` if present → use it directly.
2. Else the agency's active `RateCard` row → use it (today's behaviour).
3. Else `_fallback_model(brief)` → fallback (today's last-resort behaviour).

The override structure has the same shape as the agency rate card (`{hourly_rates, offerings, multipliers?}`), so the rest of the cost-model code — `_build_package_index`, `_ai_match`, `_build_tiered` — is unchanged. The only diff is which dict is sourced.

A line in the cost-model output records which source was used: `cost_model.source: "override" | "agency" | "fallback"`. The frontend can surface this in the cost-model card as a small badge so the user knows whether they're looking at real numbers, the master rate card, or estimates.

### Piece E — Schema change

One Alembic migration `04_proposal_rate_card_columns` adds two nullable JSON columns on `proposals`:

- `rate_card_gaps: JSON | null` — populated when the pipeline is paused awaiting fill. Shape: `{missing_roles, missing_offerings, needed_roles, needed_offerings}`.
- `rate_card_override: JSON | null` — populated by the Excel-import confirm step (and only that). Shape: `{hourly_rates, offerings, multipliers?}`.

Both default to NULL. No backfill — existing proposals keep both as NULL and behave exactly as before.

No new status enum value. The presence of `rate_card_gaps` IS the pause signal; the presence of `rate_card_override` IS the "use this instead" signal.

## Error handling

- **Gap analyzer LLM fails** (network, Bedrock 5xx, parse error). Log and treat as "no gaps detected" — pipeline proceeds to research. The cost model's existing `_fallback_model` is still there as the safety net. We do NOT block the user on an analyzer failure.
- **Excel parse fails** (corrupt file, password-protected, >5MB, not `.xlsx`). Return 400 with a structured error → red block in the chat card. User can drop a different file or fall back to the manual form.
- **Excel LLM extraction returns garbage** (invalid JSON, schema mismatch). Same as above — surface the error, let the user retry or fill manually.
- **User submits fill with keys outside the detected gaps.** Reject those keys; only entries matching `missing_roles` / `missing_offerings` are accepted. Prevents the chat from being used to silently rewrite arbitrary agency rate-card entries.
- **Pipeline race**: if `run_research` somehow gets enqueued before the fill arrives (it shouldn't — the design strictly does not enqueue when gaps are present), the cost-model phase will still consult the override / agency rate card → in the worst case it runs with fallback. Not catastrophic.

## Testing

**Backend (~8 new tests):**

- `tests/unit/test_rate_gap_analyzer.py` — sample briefs return plausible `needed_roles` / `needed_offerings`. Mocked LLM.
- `tests/integration/test_analyze_brief_detects_gaps.py` — empty rate card → proposal lands with `rate_card_gaps` populated; `run_research` is NOT enqueued.
- `tests/integration/test_analyze_brief_no_gaps.py` — fully populated rate card → no pause, research auto-enqueues. Regression for the current happy path.
- `tests/integration/test_rate_card_gaps_fill.py` — POST `/fill` merges into agency rate card, clears gaps, enqueues research. Trying to fill with a key not in `missing_*` is rejected with 400.
- `tests/integration/test_rate_card_gaps_skip.py` — POST `/skip` clears gaps without touching any rate card and enqueues research.
- `tests/integration/test_rate_card_import_upload.py` — multipart `.xlsx` upload returns a preview structure. Sample sheet exercised end-to-end with the real `openpyxl` parser; the LLM call is mocked to return a known structure.
- `tests/integration/test_rate_card_import_confirm.py` — confirm writes `proposal.rate_card_override`, clears gaps, enqueues research. Agency rate card is NOT modified.
- `tests/integration/test_cost_model_uses_override.py` — when `rate_card_override` is set, `CostModelBuilder.build` consults it (not the agency rate card). When unset, falls back to the agency. When both unset, falls back to `_fallback_model`. `cost_model.source` reflects each case.

**Frontend (~5 new tests):**

- `tests/components/chat/rate-gap-card.test.tsx` — renders form fields for `missing_roles` and `missing_offerings`; submit calls `/fill`; skip calls `/skip`.
- Excel drag-drop: drop event posts to `/rate-card-import`, preview view appears.
- Preview view confirm posts to `/rate-card-import/confirm`; cancel returns to the manual form.
- Low-confidence fields in the preview are visually flagged.
- `cost-model-card.tsx` extension: the `source: "override"|"agency"|"fallback"` badge renders correctly.

**Targets:** backend 359 → ~367; frontend 256 → ~261. Existing suites stay green.

## Future work

- **Per-client / per-engagement rate-card overrides** at the agency master level (so the agency can lock in "Horlicks always uses these rates" without re-importing per proposal).
- **"Save this override to the agency rate card"** toggle in the import confirm step.
- **Re-running gap detection** when the brief is edited.
- **Multi-currency** support in the Excel import (currency column → optional conversion or per-row tagging).
- **`.csv` and Google Sheets** import alongside `.xlsx`.
- **Inline edit** of agency master rate-card entries from the chat (not just additive fill).
