# Rate Card Onboarding Form — Design

**Status:** Brainstormed 2026-05-18. Implementation plan: pending.
**Surface:** `frontend/src/pages/onboarding/step-rate-card.tsx` only.
**Backend / API:** No changes.

---

## Goal

Replace the JSON-paste textarea in onboarding step 2 with a structured 4-sub-step wizard that captures the same data shape the JSON paste captures today.

A new user signing up should be able to set up a working rate card without knowing the JSON schema, without copy-pasting from another system, and without losing the ability to skip sections they aren't ready to fill.

## Non-goals

- **Settings → Rate Card editor (`frontend/src/pages/rate-card/editor.tsx`) is untouched.** It remains the place where existing rate cards are edited; the wizard is for first-capture only.
- No backend model, schema, repository, or viewmodel changes.
- No template / "starter rate card" feature (rejected during brainstorming — adds product complexity for the same end state).
- No versioning UI in the wizard — `version` is auto-stamped as `'v1'` on first capture. Version management already exists in the Settings editor.
- No currency configuration — rupees are baked in everywhere else in the product.
- No bulk import / CSV upload (potential follow-up if the form proves too slow in practice).
- The existing "Skip for now" mode at the top of `step-rate-card.tsx` is removed — its outcome (empty rate card with defaults) is reachable by skipping every sub-step.

## User flow

```
Onboarding step 2 of 4 (the existing top-level onboarding chrome stays)
   │
   ├─ Sub-step 2a · Offerings & Packages          (master/detail two-pane)
   │      ↓ Save & Continue   (soft-required: empty → yellow notice → advance)
   │
   ├─ Sub-step 2b · Hourly rates by role          (chips + table)
   │      ↓ Save & Continue
   │
   ├─ Sub-step 2c · Pricing multipliers           (4 fixed rows + add custom)
   │      ↓ Save & Continue
   │
   └─ Sub-step 2d · Defaults & policies            (3 fields)
          ↓ Finish rate card → advances onboarding to step 3 (voice calibration)
```

Each sub-step renders inside a shared `WizardShell` chrome:
- **Header:** progress dots `● ○ ○ ○`, sub-step title, sub-step subtitle
- **Body:** the sub-step's specific content
- **Sticky footer:** `← Back` link (hidden on 2a) + `Skip this section` link + primary `Save & Continue` button (or `Finish rate card` on 2d)

Sub-steps **never block** advancement — clicking Save & Continue with an empty or invalid section shows a one-line yellow notice ("You can fill this in later in Settings") and advances anyway. This is the *soft-required* policy chosen during brainstorming.

## Sub-step layouts

### 2a · Offerings & Packages — master/detail two-pane

- **Left rail (~35% width):** scrollable list of offerings (e.g., `BI · Brand Identity`, `DM · Digital Marketing`). Selected offering is highlighted dark. `+ Add offering` link at the bottom.
- **Right pane:** packages table for the selected offering — columns `Package`, `Description`, `Price (₹)`, `Hours (optional)`, delete. `+ Add package` link below the table.
- **Empty state:** when no offerings exist yet, the left rail shows only `+ Add offering`, and the right pane shows a one-line "Pick or add an offering to see its packages."
- **Right-pane header:** when an offering is selected, the right pane shows two editable inline inputs above the packages table — `name` (full title) and `code` (uppercase short identifier). Editing either updates the left-rail row in real time. Renames change the display label; code edits change the key under which the offering is stored in the payload.
- **Add offering flow:** clicking `+ Add offering` appends an offering with name `"New offering"` and an auto-suggested code (sequential `O1`, `O2`, …) to the left rail and selects it. The right-pane header inputs are auto-focused on `name` so the user can immediately type.
- **Add package flow:** clicking `+ Add package` appends an empty row in the table — user types name, description, price, optional hours, then blur-to-commit. Empty rows are dropped at submit time.
- **Delete:** hovering an offering row in the left rail reveals a `✕`; hovering a package row in the table reveals the same. Both prompt for confirmation only if the row has been edited (empty rows delete silently).

### 2b · Hourly rates by role — chips + table

- **Common-role chips:** dashed pills along the top — `+ Creative Director`, `+ Senior Designer`, `+ Designer`, `+ Copywriter`, `+ Art Director`, `+ Account Manager`, `+ Strategist`, `+ Developer`. Tap adds a row to the table with the role pre-filled, focuses the rate input. Tapped chips disappear from the chip row (the role is in the table now).
- **Table:** columns `Role`, `Rate (₹/hr)`, delete. Roles are snake_cased on entry (e.g., "Creative Director" → `creative_director`) — backend keys are stable but display is title-cased.
- **`+ Add custom role`** link below the table for roles outside the common set.

### 2c · Pricing multipliers — 4 fixed rows + add custom

The 4 rows for `urgency_rush`, `annual_bundle`, `existing_client`, `complexity_enterprise` are always rendered. Each row shows:
- **Header:** human-readable label (e.g., "Rush job") + the magic key in monospace (e.g., `urgency_rush`) so the user can see what hooks the cost-model uses
- **Help text:** one line explaining when the cost-model auto-applies this multiplier
- **Controls:** multiplier value input (defaults pre-filled: 1.5, 0.88, 0.95, 1.5) + free-text description input

Below the 4 fixed rows: a dashed `+ Add custom multiplier` row. Adding one shows a warning: *"Custom multipliers must be applied manually in the proposal — the cost-model only auto-applies the four above."*

Users can leave any of the 4 fixed rows at their defaults or zero them out — the cost-model treats absent multipliers as 1.0.

### 2d · Defaults & policies — 3 fields

Three labeled inputs in a horizontal grid:
- **Pass-through markup** (% input, default 10%) — *"What you charge clients on top of pass-through costs (print, photography, third-party services)"*
- **Standard options per deliverable** (integer, default 3) — *"How many design options or concepts you include in the base price for each deliverable"*
- **Standard revision rounds** (integer, default 2) — *"How many rounds of revisions are included before additional rounds are billed at hourly rates"*

Primary button on this sub-step reads `Finish rate card →` instead of `Save & Continue →`.

## Component architecture

```
step-rate-card.tsx                    REWRITTEN — thin composer (~50 LOC)
  │
  └─ <RateCardWizard onSubmit saving>     NEW — wizard state owner (~120 LOC)
        │ state: { subStep, version, offerings, hourly_rates,
        │          multipliers, pass_through_markup,
        │          standard_options, standard_revisions }
        │
        ├─ <WizardShell                     NEW — chrome
        │     subStep total title subtitle
        │     onBack onSkip onContinue
        │     continueLabel >{children}</WizardShell>
        │
        ├─ <OfferingsStep value onChange /> NEW — sub-step 2a
        │     ├─ <OfferingList .../>
        │     └─ <PackagesTable .../>
        │
        ├─ <HourlyRatesStep value onChange /> NEW — sub-step 2b
        │     ├─ COMMON_ROLES chip row
        │     └─ <RateTable .../>
        │
        ├─ <MultipliersStep value onChange /> NEW — sub-step 2c
        │     ├─ KNOWN_MULTIPLIERS pre-rendered rows
        │     └─ <CustomMultiplierRow .../>
        │
        └─ <GlobalsStep value onChange />    NEW — sub-step 2d
```

All sub-step components live in `frontend/src/components/rate-card-wizard/` (new directory). They are pure presentation — wizard state is owned by `<RateCardWizard>` and propagated via `value` / `onChange` props.

## Data shape

Wizard state mirrors the API payload exactly — no transformation at submit time. This matches the existing JSON-paste behavior, so the backend onboarding endpoint sees the same body shape it does today.

```typescript
{
  version: 'v1',                                 // hardcoded on first capture
  offerings: {
    [code: string]: {
      name: string,
      code: string,
      packages: {
        [package_key: string]: {
          base: number,
          description: string,
          typical_hours?: number,
        }
      }
    }
  },
  hourly_rates: { [role_key: string]: number },
  multipliers: {
    [key: string]: { value: number, description: string }
  },
  pass_through_markup: number,    // default 0.10
  standard_options: number,        // default 3
  standard_revisions: number,      // default 2
}
```

The wizard does not make its own HTTP call. On Finish, it calls the `onSubmit(data)` prop provided by `pages/onboarding/index.tsx` — which in turn posts to `POST /agencies/me/onboarding` with `{ step: 2, data: <the payload above> }`. This is the existing onboarding shape; the wizard reuses it without modification.

## Validation

Per-field, on blur. **Save & Continue is always enabled** per the soft-required policy — validation messages are advisory, not gating.

| Field | Rule |
|---|---|
| Offering name | required; non-empty after trim |
| Offering code | required; auto-derived from name (uppercase initials) on add; user-editable; uppercase letters + digits only |
| Package name | required; auto-snake-cased into key on commit |
| Package base price | required; ≥ 0 |
| Package typical_hours | optional; ≥ 0 if present |
| Role | required; auto-snake-cased into key on commit |
| Hourly rate | > 0 |
| Multiplier value (fixed row) | optional; ≥ 0 if present (0 means "don't apply this multiplier" — stored as omitted key in the payload) |
| Custom multiplier name | required; non-empty |
| Custom multiplier value | > 0 |
| Pass-through markup | 0–1 (rendered as %); default 0.10 |
| Standard options | integer ≥ 0; default 3 |
| Standard revisions | integer ≥ 0; default 2 |

Invalid rows show a red 1px border + an inline message in red text below the row. A sub-step counts as "valid" if every visible row passes. Clicking Save & Continue when the sub-step is empty or invalid:
- Empty → yellow notice strip *"You can fill this in later in Settings"* appears above the footer for ~2s and then the wizard advances.
- Invalid → same yellow notice with text *"Some fields look incomplete. They'll be ignored — you can fix them in Settings"* and the wizard advances, dropping invalid rows from the payload.

This non-blocking strictness is deliberate. The downstream cost-model is robust to missing data (it falls back to AI-suggested pricing when the rate card is sparse) and we want the user to get to step 3 even if they got stuck.

## Known multipliers — source of truth

```typescript
// frontend/src/components/rate-card-wizard/known-multipliers.ts
export const KNOWN_MULTIPLIERS = [
  { key: 'urgency_rush',          label: 'Rush job',              defaultValue: 1.5,  help: 'Applied when the proposal is marked as rush in the brief intake' },
  { key: 'annual_bundle',         label: 'Annual bundle',         defaultValue: 0.88, help: 'Discount when client commits to retainer or annual deal' },
  { key: 'existing_client',       label: 'Existing client',       defaultValue: 0.95, help: 'Discount for clients already in your CRM' },
  { key: 'complexity_enterprise', label: 'Enterprise complexity', defaultValue: 1.5,  help: 'Surcharge for enterprise-scale or multi-stakeholder projects' },
] as const
```

This is the **single frontend source of truth** for which multiplier keys the cost-model auto-applies. The cost-model implementation in `backend/app/services/ai/cost_model_builder.py` matches these four exact strings; a unit test (see Tests below) asserts they don't drift.

If the backend ever adds a fifth auto-applied multiplier key, this list is updated to match in the same PR.

```typescript
// frontend/src/components/rate-card-wizard/common-roles.ts
export const COMMON_ROLES = [
  'creative_director', 'senior_designer', 'designer', 'copywriter',
  'art_director', 'account_manager', 'strategist', 'developer',
]
```

## Tests

All new tests are vitest, colocated in `__tests__/` siblings of the components they cover.

| File | Coverage |
|---|---|
| `components/rate-card-wizard/__tests__/offerings-step.test.tsx` | render empty, add offering, add package, edit package, delete row, validation messages, code auto-derivation, snake-casing |
| `components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx` | render empty, chip click adds row + focuses rate, chip disappears after click, add custom role, delete row |
| `components/rate-card-wizard/__tests__/multipliers-step.test.tsx` | renders all 4 fixed rows with defaults, edit value, add custom shows warning, custom row validation |
| `components/rate-card-wizard/__tests__/globals-step.test.tsx` | render with defaults, edit each field, percent rendering of markup |
| `components/rate-card-wizard/__tests__/wizard-shell.test.tsx` | progress dots reflect subStep, back button hidden on first step, footer button label changes per step |
| `components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx` | full flow click-through 2a→2b→2c→2d→submit; back navigation preserves all sub-step state; partial-state submit produces correct payload shape; skipping all 4 sub-steps still submits with sensible defaults; invalid rows are dropped from final payload |
| `components/rate-card-wizard/__tests__/known-multipliers.test.ts` | KNOWN_MULTIPLIERS keys are exactly `['urgency_rush', 'annual_bundle', 'existing_client', 'complexity_enterprise']` — anchor test so the frontend never silently drifts from `cost_model_builder.py` |
| `pages/onboarding/__tests__/step-rate-card.test.tsx` (if it exists; new otherwise) | the rewritten thin composer renders the wizard, passes `saving` through, calls `onSubmit` on Finish |

No new backend tests. The existing coverage of `POST /api/v1/agencies/{id}/onboarding` with `step=2` continues to apply, since the API contract is unchanged.

## Acceptance criteria

A reviewer should be able to verify the slice is done by checking:

- [ ] `frontend/src/pages/onboarding/step-rate-card.tsx` no longer contains the JSON textarea or the `PLACEHOLDER` JSON constant
- [ ] New directory `frontend/src/components/rate-card-wizard/` contains the 5 sub-step components, `WizardShell`, `known-multipliers.ts`, `common-roles.ts`
- [ ] Walking through onboarding produces 4 sub-step screens in order, each with the chrome described above
- [ ] All 4 sub-steps can be skipped; the wizard advances; final submit produces a valid (possibly mostly-empty) rate card row in `rate_cards` table
- [ ] Filling all 4 sub-steps and clicking Finish produces a payload with the same shape as the JSON paste used to produce
- [ ] `pnpm test --run` includes the new tests and they pass
- [ ] `pnpm build` is clean

## Open questions

None — all design decisions were resolved during brainstorming.

## Future work (post-merge)

- CSV/spreadsheet upload as an alternative entry mode to the wizard (only build if first-time-completion telemetry shows the wizard is too slow)
- A "duplicate from another agency" import flow if multi-agency support arrives
- Multi-currency support once the rest of the product supports it
