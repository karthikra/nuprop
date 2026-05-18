# Rate Card Onboarding Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the JSON-paste textarea in onboarding step 2 (`frontend/src/pages/onboarding/step-rate-card.tsx`) with a 4-sub-step wizard that captures Offerings, Hourly Rates, Multipliers, and Globals via structured form controls.

**Architecture:** Pure frontend change. Adds a new `frontend/src/components/rate-card-wizard/` directory with a stateful `<RateCardWizard>` composer + 4 stateless sub-step components + a shared `<WizardShell>` chrome. The onboarding page (`pages/onboarding/index.tsx`) passes the same `onSubmit(data)` callback as before — backend API contract is unchanged.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, vitest + @testing-library/react + @testing-library/user-event.

**Spec:** `docs/superpowers/specs/2026-05-18-rate-card-form-design.md`

**Run commands (from `frontend/`):**
- Single test file: `pnpm vitest run src/components/rate-card-wizard/__tests__/<file>.test.tsx`
- All tests: `pnpm test`
- Build (incl. typecheck): `pnpm build`
- Lint: `pnpm lint`

---

## File Structure

**Created (all under `frontend/src/components/rate-card-wizard/`):**
- `types.ts` — `RateCardPayload`, default values
- `keys.ts` — `toSnakeKey()`, `nextOfferingCode()` pure helpers
- `known-multipliers.ts` — 4 fixed multiplier definitions
- `common-roles.ts` — 8 chip-suggested role keys
- `wizard-shell.tsx` — chrome: progress dots, header, body slot, sticky footer with optional yellow notice
- `globals-step.tsx` — sub-step 2d (3 fields)
- `hourly-rates-step.tsx` — sub-step 2b (chips + table)
- `multipliers-step.tsx` — sub-step 2c (4 fixed rows + custom)
- `offerings-step.tsx` — sub-step 2a (master/detail two-pane)
- `rate-card-wizard.tsx` — owns state, navigates sub-steps, filters payload, calls `onSubmit`
- `index.ts` — barrel export of `RateCardWizard`
- `__tests__/keys.test.ts`
- `__tests__/known-multipliers.test.ts`
- `__tests__/wizard-shell.test.tsx`
- `__tests__/globals-step.test.tsx`
- `__tests__/hourly-rates-step.test.tsx`
- `__tests__/multipliers-step.test.tsx`
- `__tests__/offerings-step.test.tsx`
- `__tests__/rate-card-wizard.test.tsx`

**Modified:**
- `frontend/src/pages/onboarding/step-rate-card.tsx` — REWRITTEN as a thin composer (~15 LOC)

**Untouched (verified during brainstorming):**
- `frontend/src/pages/onboarding/index.tsx` — invokes `<StepRateCard onSubmit={...} saving={saving} />`; the same prop contract is preserved
- `frontend/src/pages/rate-card/editor.tsx` — Settings editor; out of scope
- `frontend/src/types/rate-card.ts` — existing `Offering`, `Package`, `Multiplier` types are reused
- All backend code, schemas, and onboarding endpoint

---

## Task 1: Scaffold types + key helpers

**Files:**
- Create: `frontend/src/components/rate-card-wizard/types.ts`
- Create: `frontend/src/components/rate-card-wizard/keys.ts`
- Create: `frontend/src/components/rate-card-wizard/__tests__/keys.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/keys.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { toSnakeKey, nextOfferingCode } from '../keys'

describe('toSnakeKey', () => {
  it('lowercases and snake_cases ASCII words', () => {
    expect(toSnakeKey('Creative Director')).toBe('creative_director')
  })

  it('collapses runs of non-alphanumeric characters into a single underscore', () => {
    expect(toSnakeKey('Logo  &  Identity!!')).toBe('logo_identity')
  })

  it('strips leading and trailing underscores', () => {
    expect(toSnakeKey('  --foo--  ')).toBe('foo')
  })

  it('returns "untitled" for empty or all-noise input', () => {
    expect(toSnakeKey('')).toBe('untitled')
    expect(toSnakeKey('   ')).toBe('untitled')
    expect(toSnakeKey('!!!')).toBe('untitled')
  })
})

describe('nextOfferingCode', () => {
  it('returns O1 when no offerings exist', () => {
    expect(nextOfferingCode({})).toBe('O1')
  })

  it('skips taken codes', () => {
    expect(nextOfferingCode({ O1: {}, O2: {} })).toBe('O3')
  })

  it('ignores non-O-prefixed keys', () => {
    expect(nextOfferingCode({ BI: {}, DM: {} })).toBe('O1')
  })

  it('fills gaps', () => {
    expect(nextOfferingCode({ O1: {}, O3: {} })).toBe('O2')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/keys.test.ts`
Expected: FAIL with module-not-found for `../keys`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/keys.ts`:

```typescript
/** Convert a human-readable label into a stable snake_case key. */
export function toSnakeKey(label: string): string {
  const cleaned = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return cleaned || 'untitled'
}

/** Return the next free O-prefixed code (O1, O2, ...) given existing offerings. */
export function nextOfferingCode(existing: Record<string, unknown>): string {
  let i = 1
  while (`O${i}` in existing) i++
  return `O${i}`
}
```

Create `frontend/src/components/rate-card-wizard/types.ts`:

```typescript
import type { Offering, Multiplier } from '../../types/rate-card'

/** The exact JSON shape posted to `POST /agencies/me/onboarding` with step=2. */
export interface RateCardPayload {
  version: string
  offerings: Record<string, Offering>
  hourly_rates: Record<string, number>
  multipliers: Record<string, Multiplier>
  pass_through_markup: number
  standard_options: number
  standard_revisions: number
}

/** Defaults applied to any field the user skips. Mirrors agency_viewmodel.py:69-77. */
export const DEFAULT_PAYLOAD: RateCardPayload = {
  version: 'v1',
  offerings: {},
  hourly_rates: {},
  multipliers: {},
  pass_through_markup: 0.10,
  standard_options: 3,
  standard_revisions: 2,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/keys.test.ts`
Expected: PASS — 4 tests in `toSnakeKey`, 4 tests in `nextOfferingCode`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/keys.ts \
        frontend/src/components/rate-card-wizard/types.ts \
        frontend/src/components/rate-card-wizard/__tests__/keys.test.ts
git commit -m "feat(rate-card): add key helpers and payload types"
```

---

## Task 2: Add known-multipliers and common-roles constants

**Files:**
- Create: `frontend/src/components/rate-card-wizard/known-multipliers.ts`
- Create: `frontend/src/components/rate-card-wizard/common-roles.ts`
- Create: `frontend/src/components/rate-card-wizard/__tests__/known-multipliers.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/known-multipliers.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { KNOWN_MULTIPLIERS } from '../known-multipliers'

/**
 * This test is an anchor — it locks the four multiplier keys the frontend
 * pre-builds rows for to the four keys the backend cost-model auto-applies
 * (see backend/app/services/ai/cost_model_builder.py lines ~127-160).
 *
 * If you change either side, change both — and update this test to match.
 */
describe('KNOWN_MULTIPLIERS', () => {
  it('has exactly the four keys the cost-model auto-applies', () => {
    expect(KNOWN_MULTIPLIERS.map((m) => m.key)).toEqual([
      'urgency_rush',
      'annual_bundle',
      'existing_client',
      'complexity_enterprise',
    ])
  })

  it('provides a label, default value, and help text for each row', () => {
    for (const m of KNOWN_MULTIPLIERS) {
      expect(m.label).toBeTruthy()
      expect(typeof m.defaultValue).toBe('number')
      expect(m.help.length).toBeGreaterThan(20)
    }
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/known-multipliers.test.ts`
Expected: FAIL with module-not-found for `../known-multipliers`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/known-multipliers.ts`:

```typescript
/**
 * The four multiplier keys the backend cost-model (`cost_model_builder.py`)
 * auto-applies based on proposal context. Keep these in sync with that file —
 * the anchor test in __tests__/known-multipliers.test.ts enforces the contract.
 */
export const KNOWN_MULTIPLIERS = [
  {
    key: 'urgency_rush',
    label: 'Rush job',
    defaultValue: 1.5,
    help: 'Applied when the proposal is marked as rush in the brief intake',
  },
  {
    key: 'annual_bundle',
    label: 'Annual bundle',
    defaultValue: 0.88,
    help: 'Discount when client commits to retainer or annual deal',
  },
  {
    key: 'existing_client',
    label: 'Existing client',
    defaultValue: 0.95,
    help: 'Discount for clients already in your CRM',
  },
  {
    key: 'complexity_enterprise',
    label: 'Enterprise complexity',
    defaultValue: 1.5,
    help: 'Surcharge for enterprise-scale or multi-stakeholder projects',
  },
] as const

export type KnownMultiplierKey = (typeof KNOWN_MULTIPLIERS)[number]['key']
```

Create `frontend/src/components/rate-card-wizard/common-roles.ts`:

```typescript
/** Roles offered as quick-add chips on sub-step 2b. Keys are already snake_case. */
export const COMMON_ROLES: { key: string; label: string }[] = [
  { key: 'creative_director', label: 'Creative Director' },
  { key: 'senior_designer',   label: 'Senior Designer' },
  { key: 'designer',          label: 'Designer' },
  { key: 'copywriter',        label: 'Copywriter' },
  { key: 'art_director',      label: 'Art Director' },
  { key: 'account_manager',   label: 'Account Manager' },
  { key: 'strategist',        label: 'Strategist' },
  { key: 'developer',         label: 'Developer' },
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/known-multipliers.test.ts`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/known-multipliers.ts \
        frontend/src/components/rate-card-wizard/common-roles.ts \
        frontend/src/components/rate-card-wizard/__tests__/known-multipliers.test.ts
git commit -m "feat(rate-card): add known-multipliers and common-roles constants"
```

---

## Task 3: WizardShell chrome

**Files:**
- Create: `frontend/src/components/rate-card-wizard/wizard-shell.tsx`
- Create: `frontend/src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WizardShell } from '../wizard-shell'

function setup(props: Partial<React.ComponentProps<typeof WizardShell>> = {}) {
  const onSkip = vi.fn()
  const onContinue = vi.fn()
  const onBack = vi.fn()
  render(
    <WizardShell
      subStep={0}
      total={4}
      title="Test step"
      subtitle="Hi"
      onBack={onBack}
      onSkip={onSkip}
      onContinue={onContinue}
      {...props}
    >
      <div data-testid="body">body content</div>
    </WizardShell>,
  )
  return { onBack, onSkip, onContinue }
}

describe('WizardShell', () => {
  it('renders the title, subtitle, and body slot', () => {
    setup()
    expect(screen.getByText('Test step')).toBeInTheDocument()
    expect(screen.getByText('Hi')).toBeInTheDocument()
    expect(screen.getByTestId('body')).toBeInTheDocument()
  })

  it('renders a dot per sub-step with the active one highlighted', () => {
    setup({ subStep: 2, total: 4 })
    const dots = screen.getAllByTestId('wizard-dot')
    expect(dots).toHaveLength(4)
    expect(dots[2]).toHaveAttribute('data-active', 'true')
    expect(dots[0]).toHaveAttribute('data-active', 'false')
  })

  it('hides the Back link when onBack is not provided', () => {
    setup({ onBack: undefined })
    expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
  })

  it('uses the default continue label "Save & Continue"', () => {
    setup()
    expect(screen.getByRole('button', { name: /save & continue/i })).toBeInTheDocument()
  })

  it('uses a custom continue label when provided', () => {
    setup({ continueLabel: 'Finish rate card' })
    expect(screen.getByRole('button', { name: /finish rate card/i })).toBeInTheDocument()
  })

  it('calls onSkip when the skip link is clicked', async () => {
    const user = userEvent.setup()
    const { onSkip } = setup()
    await user.click(screen.getByRole('button', { name: /skip this section/i }))
    expect(onSkip).toHaveBeenCalledOnce()
  })

  it('calls onContinue when the primary button is clicked', async () => {
    const user = userEvent.setup()
    const { onContinue } = setup()
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(onContinue).toHaveBeenCalledOnce()
  })

  it('renders a yellow notice strip when notice prop is set', () => {
    setup({ notice: 'You can fill this in later in Settings' })
    expect(screen.getByText(/fill this in later/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx`
Expected: FAIL with module-not-found for `../wizard-shell`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/wizard-shell.tsx`:

```typescript
import type { ReactNode } from 'react'

interface Props {
  subStep: number
  total: number
  title: string
  subtitle: string
  children: ReactNode
  onBack?: () => void
  onSkip: () => void
  onContinue: () => void
  continueLabel?: string
  notice?: string
}

export function WizardShell({
  subStep,
  total,
  title,
  subtitle,
  children,
  onBack,
  onSkip,
  onContinue,
  continueLabel = 'Save & Continue →',
  notice,
}: Props) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <div className="px-5 py-4 border-b border-stone-200">
        <div className="flex gap-1.5 mb-2" aria-label={`Sub-step ${subStep + 1} of ${total}`}>
          {Array.from({ length: total }).map((_, i) => (
            <div
              key={i}
              data-testid="wizard-dot"
              data-active={i === subStep ? 'true' : 'false'}
              className={`w-1.5 h-1.5 rounded-full ${i === subStep ? 'bg-stone-900' : 'bg-stone-300'}`}
            />
          ))}
        </div>
        <h2 className="text-base font-semibold text-stone-900">{title}</h2>
        <p className="text-xs text-stone-500 mt-0.5">{subtitle}</p>
      </div>

      <div className="px-5 py-5">{children}</div>

      {notice && (
        <div className="px-5 py-2 text-xs text-amber-800 bg-amber-50 border-t border-amber-200">
          {notice}
        </div>
      )}

      <div className="px-5 py-3 border-t border-stone-200 bg-stone-50 flex items-center justify-between">
        <div className="flex gap-3 text-xs text-stone-500">
          {onBack && (
            <button onClick={onBack} className="hover:text-stone-900">
              ← Back
            </button>
          )}
          <button onClick={onSkip} className="hover:text-stone-900">
            Skip this section
          </button>
        </div>
        <button
          onClick={onContinue}
          className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-stone-800"
        >
          {continueLabel}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/wizard-shell.tsx \
        frontend/src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx
git commit -m "feat(rate-card): WizardShell chrome with progress dots and sticky footer"
```

---

## Task 4: GlobalsStep (sub-step 2d, simplest)

**Files:**
- Create: `frontend/src/components/rate-card-wizard/globals-step.tsx`
- Create: `frontend/src/components/rate-card-wizard/__tests__/globals-step.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/globals-step.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GlobalsStep } from '../globals-step'

const DEFAULTS = { pass_through_markup: 0.10, standard_options: 3, standard_revisions: 2 }

describe('GlobalsStep', () => {
  it('renders all three fields with their default values', () => {
    render(<GlobalsStep value={DEFAULTS} onChange={vi.fn()} />)
    expect(screen.getByLabelText(/pass-through markup/i)).toHaveValue(10)
    expect(screen.getByLabelText(/standard options/i)).toHaveValue(3)
    expect(screen.getByLabelText(/standard revision rounds/i)).toHaveValue(2)
  })

  it('calls onChange with the new pass-through markup as a decimal', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/pass-through markup/i)
    await user.clear(input)
    await user.type(input, '15')
    // The last call should reflect 15% = 0.15
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, pass_through_markup: 0.15 })
  })

  it('calls onChange when standard options is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/standard options/i)
    await user.clear(input)
    await user.type(input, '5')
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, standard_options: 5 })
  })

  it('calls onChange when standard revisions is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/standard revision rounds/i)
    await user.clear(input)
    await user.type(input, '4')
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, standard_revisions: 4 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/globals-step.test.tsx`
Expected: FAIL with module-not-found for `../globals-step`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/globals-step.tsx`:

```typescript
export interface GlobalsValue {
  pass_through_markup: number
  standard_options: number
  standard_revisions: number
}

interface Props {
  value: GlobalsValue
  onChange: (next: GlobalsValue) => void
}

export function GlobalsStep({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
      <Field
        label="Pass-through markup"
        suffix="%"
        help="What you charge clients on top of pass-through costs (print, photography, third-party services)"
        value={Math.round(value.pass_through_markup * 100)}
        onChange={(v) => onChange({ ...value, pass_through_markup: v / 100 })}
      />
      <Field
        label="Standard options per deliverable"
        help="How many design options or concepts you include in the base price for each deliverable"
        value={value.standard_options}
        onChange={(v) => onChange({ ...value, standard_options: v })}
      />
      <Field
        label="Standard revision rounds"
        help="How many rounds of revisions are included before additional rounds are billed at hourly rates"
        value={value.standard_revisions}
        onChange={(v) => onChange({ ...value, standard_revisions: v })}
      />
    </div>
  )
}

function Field({
  label,
  suffix,
  help,
  value,
  onChange,
}: {
  label: string
  suffix?: string
  help: string
  value: number
  onChange: (n: number) => void
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-stone-900 mb-1">{label}</span>
      <div className="flex items-center gap-1">
        <input
          type="number"
          aria-label={label}
          value={value}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-stone-900"
        />
        {suffix && <span className="text-sm text-stone-500">{suffix}</span>}
      </div>
      <p className="text-xs text-stone-500 mt-1 leading-snug">{help}</p>
    </label>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/globals-step.test.tsx`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/globals-step.tsx \
        frontend/src/components/rate-card-wizard/__tests__/globals-step.test.tsx
git commit -m "feat(rate-card): GlobalsStep (2d) — 3 fields with help text"
```

---

## Task 5: HourlyRatesStep (sub-step 2b)

**Files:**
- Create: `frontend/src/components/rate-card-wizard/hourly-rates-step.tsx`
- Create: `frontend/src/components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HourlyRatesStep } from '../hourly-rates-step'

describe('HourlyRatesStep', () => {
  it('renders 8 common-role chips when value is empty', () => {
    render(<HourlyRatesStep value={{}} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /\+ creative director/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+ developer/i })).toBeInTheDocument()
    // 8 chips
    expect(screen.getAllByRole('button', { name: /^\+ / }).length).toBe(8)
  })

  it('hides chips that already exist in the rates table', () => {
    render(<HourlyRatesStep value={{ creative_director: 6000 }} onChange={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /\+ creative director/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+ designer/i })).toBeInTheDocument()
  })

  it('adds a row when a chip is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<HourlyRatesStep value={{}} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ designer/i }))
    expect(onChange).toHaveBeenCalledWith({ designer: 0 })
  })

  it('updates a rate when the user edits the rate input', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<HourlyRatesStep value={{ designer: 0 }} onChange={onChange} />)
    const input = screen.getByLabelText(/rate for designer/i)
    await user.clear(input)
    await user.type(input, '4000')
    expect(onChange).toHaveBeenLastCalledWith({ designer: 4000 })
  })

  it('deletes a row when the delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<HourlyRatesStep value={{ designer: 4000 }} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete designer/i }))
    expect(onChange).toHaveBeenCalledWith({})
  })

  it('adds a custom role with auto snake_cased key', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<HourlyRatesStep value={{}} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /add custom role/i }))
    const nameInput = screen.getByPlaceholderText(/role name/i)
    await user.type(nameInput, 'Motion Designer')
    await user.tab() // blur to commit
    expect(onChange).toHaveBeenCalledWith({ motion_designer: 0 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx`
Expected: FAIL with module-not-found for `../hourly-rates-step`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/hourly-rates-step.tsx`:

```typescript
import { useState } from 'react'
import { COMMON_ROLES } from './common-roles'
import { toSnakeKey } from './keys'

interface Props {
  value: Record<string, number>
  onChange: (next: Record<string, number>) => void
}

export function HourlyRatesStep({ value, onChange }: Props) {
  const [addingCustom, setAddingCustom] = useState(false)
  const [customName, setCustomName] = useState('')

  const availableChips = COMMON_ROLES.filter((r) => !(r.key in value))
  const rows = Object.entries(value)

  const addChip = (key: string) => onChange({ ...value, [key]: 0 })

  const updateRate = (key: string, rate: number) => onChange({ ...value, [key]: rate })

  const deleteRow = (key: string) => {
    const next = { ...value }
    delete next[key]
    onChange(next)
  }

  const commitCustom = () => {
    const trimmed = customName.trim()
    if (!trimmed) {
      setAddingCustom(false)
      return
    }
    const key = toSnakeKey(trimmed)
    if (!(key in value)) onChange({ ...value, [key]: 0 })
    setCustomName('')
    setAddingCustom(false)
  }

  const prettify = (key: string): string => {
    const common = COMMON_ROLES.find((r) => r.key === key)
    if (common) return common.label
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  return (
    <div className="space-y-4">
      {availableChips.length > 0 && (
        <>
          <p className="text-xs text-stone-500">Tap a common role to add it instantly</p>
          <div className="flex flex-wrap gap-2">
            {availableChips.map((r) => (
              <button
                key={r.key}
                onClick={() => addChip(r.key)}
                className="rounded-full border border-dashed border-stone-300 bg-stone-50 px-3 py-1 text-xs text-stone-600 hover:bg-stone-100"
              >
                + {r.label}
              </button>
            ))}
          </div>
        </>
      )}

      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-stone-400 uppercase tracking-wider">
              <th className="text-left py-2 font-medium">Role</th>
              <th className="text-right py-2 font-medium">Rate (₹/hr)</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map(([key, rate]) => (
              <tr key={key}>
                <td className="py-2 font-medium text-stone-900">{prettify(key)}</td>
                <td className="py-2 text-right">
                  <input
                    type="number"
                    aria-label={`Rate for ${prettify(key)}`}
                    value={rate}
                    onChange={(e) => updateRate(key, Number(e.target.value) || 0)}
                    className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                  />
                </td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => deleteRow(key)}
                    aria-label={`Delete ${prettify(key)}`}
                    className="text-stone-300 hover:text-red-500 text-sm"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {addingCustom ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Role name (e.g. Motion Designer)"
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            onBlur={commitCustom}
            onKeyDown={(e) => { if (e.key === 'Enter') commitCustom() }}
            autoFocus
            className="w-64 rounded-md border border-stone-300 px-2 py-1 text-sm"
          />
        </div>
      ) : (
        <button
          onClick={() => setAddingCustom(true)}
          className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900"
        >
          + Add custom role
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/hourly-rates-step.tsx \
        frontend/src/components/rate-card-wizard/__tests__/hourly-rates-step.test.tsx
git commit -m "feat(rate-card): HourlyRatesStep (2b) — chips + table + custom role"
```

---

## Task 6: MultipliersStep (sub-step 2c)

**Files:**
- Create: `frontend/src/components/rate-card-wizard/multipliers-step.tsx`
- Create: `frontend/src/components/rate-card-wizard/__tests__/multipliers-step.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/multipliers-step.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MultipliersStep } from '../multipliers-step'

describe('MultipliersStep', () => {
  it('renders all 4 fixed rows with their default values', () => {
    render(<MultipliersStep value={{}} onChange={vi.fn()} />)
    expect(screen.getByText('Rush job')).toBeInTheDocument()
    expect(screen.getByText('urgency_rush')).toBeInTheDocument()
    expect(screen.getByText('Annual bundle')).toBeInTheDocument()
    expect(screen.getByText('annual_bundle')).toBeInTheDocument()
    expect(screen.getByText('Existing client')).toBeInTheDocument()
    expect(screen.getByText('Enterprise complexity')).toBeInTheDocument()
    // Defaults visible in their value inputs
    expect(screen.getByLabelText(/value for rush job/i)).toHaveValue(1.5)
    expect(screen.getByLabelText(/value for annual bundle/i)).toHaveValue(0.88)
    expect(screen.getByLabelText(/value for existing client/i)).toHaveValue(0.95)
    expect(screen.getByLabelText(/value for enterprise complexity/i)).toHaveValue(1.5)
  })

  it('uses the existing value if one is already in props', () => {
    render(<MultipliersStep value={{ urgency_rush: { value: 2.0, description: 'custom' } }} onChange={vi.fn()} />)
    expect(screen.getByLabelText(/value for rush job/i)).toHaveValue(2.0)
    expect(screen.getByDisplayValue('custom')).toBeInTheDocument()
  })

  it('calls onChange when a fixed-row value is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MultipliersStep value={{}} onChange={onChange} />)
    const input = screen.getByLabelText(/value for rush job/i)
    await user.clear(input)
    await user.type(input, '2')
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      urgency_rush: { value: 2, description: '' },
    }))
  })

  it('shows a warning when the Add custom button is clicked', async () => {
    const user = userEvent.setup()
    render(<MultipliersStep value={{}} onChange={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /add custom multiplier/i }))
    expect(screen.getByText(/cost-model only auto-applies the four above/i)).toBeInTheDocument()
  })

  it('adds a custom multiplier with snake_cased key on commit', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MultipliersStep value={{}} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /add custom multiplier/i }))
    await user.type(screen.getByPlaceholderText(/multiplier name/i), 'New Client')
    await user.type(screen.getByPlaceholderText(/value/i), '1.2')
    await user.click(screen.getByRole('button', { name: /save custom/i }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      new_client: { value: 1.2, description: '' },
    }))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/multipliers-step.test.tsx`
Expected: FAIL with module-not-found for `../multipliers-step`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/multipliers-step.tsx`:

```typescript
import { useState } from 'react'
import type { Multiplier } from '../../types/rate-card'
import { KNOWN_MULTIPLIERS } from './known-multipliers'
import { toSnakeKey } from './keys'

interface Props {
  value: Record<string, Multiplier>
  onChange: (next: Record<string, Multiplier>) => void
}

export function MultipliersStep({ value, onChange }: Props) {
  const [addingCustom, setAddingCustom] = useState(false)
  const [customName, setCustomName] = useState('')
  const [customValue, setCustomValue] = useState('1.0')

  const updateFixed = (key: string, patch: Partial<Multiplier>) => {
    const current = value[key]
    const base = current ?? {
      value: KNOWN_MULTIPLIERS.find((m) => m.key === key)?.defaultValue ?? 1.0,
      description: '',
    }
    onChange({ ...value, [key]: { ...base, ...patch } })
  }

  const commitCustom = () => {
    const trimmed = customName.trim()
    const numericValue = parseFloat(customValue)
    if (!trimmed || !Number.isFinite(numericValue) || numericValue <= 0) {
      setAddingCustom(false)
      setCustomName('')
      setCustomValue('1.0')
      return
    }
    const key = toSnakeKey(trimmed)
    onChange({ ...value, [key]: { value: numericValue, description: '' } })
    setAddingCustom(false)
    setCustomName('')
    setCustomValue('1.0')
  }

  const customEntries = Object.entries(value).filter(
    ([k]) => !KNOWN_MULTIPLIERS.some((m) => m.key === k),
  )

  return (
    <div className="space-y-3">
      {KNOWN_MULTIPLIERS.map((m) => {
        const current = value[m.key]
        const displayValue = current?.value ?? m.defaultValue
        const displayDescription = current?.description ?? ''
        return (
          <div key={m.key} className="rounded-lg border border-stone-200 p-3">
            <div className="flex items-baseline justify-between mb-1">
              <div>
                <span className="text-sm font-medium text-stone-900">{m.label}</span>
                <span className="ml-2 font-mono text-xs text-stone-400">{m.key}</span>
              </div>
            </div>
            <p className="text-xs text-stone-500 mb-2">{m.help}</p>
            <div className="flex items-center gap-3">
              <label className="text-xs text-stone-500">Multiplier</label>
              <input
                type="number"
                step="0.01"
                aria-label={`Value for ${m.label}`}
                value={displayValue}
                onChange={(e) => updateFixed(m.key, { value: Number(e.target.value) || 0 })}
                className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <label className="text-xs text-stone-500 ml-2">Note</label>
              <input
                type="text"
                aria-label={`Description for ${m.label}`}
                placeholder="Optional description"
                value={displayDescription}
                onChange={(e) => updateFixed(m.key, { description: e.target.value })}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
            </div>
          </div>
        )
      })}

      {customEntries.map(([key, m]) => (
        <div key={key} className="rounded-lg border border-dashed border-stone-300 p-3">
          <div className="flex items-baseline justify-between mb-1">
            <span className="font-mono text-xs text-stone-600">{key}</span>
            <button
              onClick={() => {
                const next = { ...value }
                delete next[key]
                onChange(next)
              }}
              aria-label={`Delete ${key}`}
              className="text-stone-300 hover:text-red-500 text-xs"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-stone-500">Multiplier</label>
            <input
              type="number"
              step="0.01"
              aria-label={`Value for ${key}`}
              value={m.value}
              onChange={(e) => onChange({ ...value, [key]: { ...m, value: Number(e.target.value) || 0 } })}
              className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <label className="text-xs text-stone-500 ml-2">Note</label>
            <input
              type="text"
              value={m.description}
              onChange={(e) => onChange({ ...value, [key]: { ...m, description: e.target.value } })}
              className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
          </div>
        </div>
      ))}

      {addingCustom ? (
        <div className="rounded-lg border border-dashed border-stone-300 p-3 space-y-2">
          <p className="text-xs text-amber-700">
            Custom multipliers must be applied manually in the proposal — the cost-model only auto-applies the four above.
          </p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Multiplier name (e.g. New client)"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              autoFocus
            />
            <input
              type="number"
              step="0.01"
              placeholder="Value (e.g. 1.2)"
              value={customValue}
              onChange={(e) => setCustomValue(e.target.value)}
              className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <button
              onClick={commitCustom}
              className="rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white"
            >
              Save custom
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAddingCustom(true)}
          className="text-xs text-stone-600 border-b border-dashed border-stone-400 hover:text-stone-900"
        >
          + Add custom multiplier
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/multipliers-step.test.tsx`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/multipliers-step.tsx \
        frontend/src/components/rate-card-wizard/__tests__/multipliers-step.test.tsx
git commit -m "feat(rate-card): MultipliersStep (2c) — 4 fixed rows + custom with warning"
```

---

## Task 7: OfferingsStep (sub-step 2a, heaviest)

**Files:**
- Create: `frontend/src/components/rate-card-wizard/offerings-step.tsx`
- Create: `frontend/src/components/rate-card-wizard/__tests__/offerings-step.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/offerings-step.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Offering } from '../../../types/rate-card'
import { OfferingsStep } from '../offerings-step'

// jsdom doesn't implement window.confirm — stub it so deleteOffering proceeds.
beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const SAMPLE: Record<string, Offering> = {
  BI: {
    name: 'Brand Identity',
    code: 'BI',
    packages: {
      logo_design: { base: 150000, description: 'Logo + 2 variations', typical_hours: 40 },
    },
  },
}

describe('OfferingsStep', () => {
  it('renders an empty state when no offerings exist', () => {
    render(<OfferingsStep value={{}} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /\+ add offering/i })).toBeInTheDocument()
    expect(screen.getByText(/pick or add an offering/i)).toBeInTheDocument()
  })

  it('appends a new offering with auto code O1 when Add offering is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={{}} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))
    expect(onChange).toHaveBeenCalledWith({
      O1: { name: 'New offering', code: 'O1', packages: {} },
    })
  })

  it('shows the selected offering in the left rail and packages in the right pane', () => {
    render(<OfferingsStep value={SAMPLE} onChange={vi.fn()} />)
    expect(screen.getByText(/BI · Brand Identity/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('Brand Identity')
    expect(screen.getByLabelText(/offering code/i)).toHaveValue('BI')
    expect(screen.getByText('Logo Design')).toBeInTheDocument()
  })

  it('updates the offering name when the right-pane name input is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={SAMPLE} onChange={onChange} />)
    const nameInput = screen.getByLabelText(/offering name/i)
    await user.clear(nameInput)
    await user.type(nameInput, 'Brand Design')
    expect(onChange).toHaveBeenLastCalledWith({
      BI: { ...SAMPLE.BI, name: 'Brand Design' },
    })
  })

  it('re-keys the offering map when the code is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={SAMPLE} onChange={onChange} />)
    const codeInput = screen.getByLabelText(/offering code/i)
    await user.clear(codeInput)
    await user.type(codeInput, 'BR')
    // Last call should have re-keyed BI → BR
    expect(onChange).toHaveBeenLastCalledWith({
      BR: { ...SAMPLE.BI, code: 'BR' },
    })
  })

  it('adds a package row when Add package is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ add package/i }))
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      BI: expect.objectContaining({
        packages: expect.objectContaining({
          new_package: { base: 0, description: '', typical_hours: 0 },
        }),
      }),
    }))
  })

  it('deletes a package row when the package delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete logo design/i }))
    expect(onChange).toHaveBeenLastCalledWith({
      BI: { ...SAMPLE.BI, packages: {} },
    })
  })

  it('deletes the offering when the offering delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<OfferingsStep value={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete offering brand identity/i }))
    expect(onChange).toHaveBeenLastCalledWith({})
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/offerings-step.test.tsx`
Expected: FAIL with module-not-found for `../offerings-step`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/offerings-step.tsx`:

```typescript
import { useEffect, useState } from 'react'
import type { Offering, Package } from '../../types/rate-card'
import { nextOfferingCode, toSnakeKey } from './keys'

interface Props {
  value: Record<string, Offering>
  onChange: (next: Record<string, Offering>) => void
}

function prettify(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function OfferingsStep({ value, onChange }: Props) {
  const codes = Object.keys(value)
  const [selectedCode, setSelectedCode] = useState<string | null>(codes[0] ?? null)

  // Keep the selection sane when offerings list changes (e.g. after delete).
  useEffect(() => {
    if (selectedCode && !(selectedCode in value)) {
      const remaining = Object.keys(value)
      setSelectedCode(remaining[0] ?? null)
    }
  }, [value, selectedCode])

  const addOffering = () => {
    const code = nextOfferingCode(value)
    onChange({ ...value, [code]: { name: 'New offering', code, packages: {} } })
    setSelectedCode(code)
  }

  const deleteOffering = (code: string) => {
    if (!confirm(`Delete offering "${value[code].name}"?`)) return
    const next = { ...value }
    delete next[code]
    onChange(next)
    if (selectedCode === code) setSelectedCode(Object.keys(next)[0] ?? null)
  }

  const updateOffering = (code: string, patch: Partial<Offering>) => {
    if (patch.code && patch.code !== code) {
      const next = { ...value }
      const oldOffering = next[code]
      delete next[code]
      next[patch.code] = { ...oldOffering, ...patch }
      onChange(next)
      setSelectedCode(patch.code)
    } else {
      onChange({ ...value, [code]: { ...value[code], ...patch } })
    }
  }

  const addPackage = (code: string) => {
    const offering = value[code]
    let key = 'new_package'
    let i = 1
    while (key in offering.packages) {
      key = `new_package_${++i}`
    }
    updateOffering(code, {
      packages: { ...offering.packages, [key]: { base: 0, description: '', typical_hours: 0 } },
    })
  }

  const updatePackage = (code: string, pkgKey: string, patch: Partial<Package>) => {
    const offering = value[code]
    updateOffering(code, {
      packages: { ...offering.packages, [pkgKey]: { ...offering.packages[pkgKey], ...patch } },
    })
  }

  const renamePackage = (code: string, oldKey: string, newName: string) => {
    const offering = value[code]
    const newKey = toSnakeKey(newName)
    if (newKey === oldKey || newKey in offering.packages) {
      updatePackage(code, oldKey, { description: offering.packages[oldKey].description })
      return
    }
    const nextPackages: Record<string, Package> = {}
    for (const [k, v] of Object.entries(offering.packages)) {
      nextPackages[k === oldKey ? newKey : k] = v
    }
    updateOffering(code, { packages: nextPackages })
  }

  const deletePackage = (code: string, pkgKey: string) => {
    const offering = value[code]
    const nextPackages = { ...offering.packages }
    delete nextPackages[pkgKey]
    updateOffering(code, { packages: nextPackages })
  }

  const selected = selectedCode ? value[selectedCode] : null

  return (
    <div className="flex gap-4 min-h-[260px]">
      {/* Left rail */}
      <div className="w-1/3 border-r border-stone-200 pr-3 space-y-1">
        {codes.map((c) => (
          <div
            key={c}
            onClick={() => setSelectedCode(c)}
            className={`group flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer text-sm ${
              c === selectedCode ? 'bg-stone-900 text-white' : 'hover:bg-stone-100 text-stone-700'
            }`}
          >
            <span>{c} · {value[c].name}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteOffering(c) }}
              aria-label={`Delete offering ${value[c].name}`}
              className="opacity-0 group-hover:opacity-100 text-xs"
            >✕</button>
          </div>
        ))}
        <button
          onClick={addOffering}
          className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900 mt-2"
        >
          + Add offering
        </button>
      </div>

      {/* Right pane */}
      <div className="flex-1">
        {!selected && (
          <p className="text-sm text-stone-400 italic">Pick or add an offering to see its packages.</p>
        )}
        {selected && (
          <>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                aria-label="Offering name"
                value={selected.name}
                onChange={(e) => updateOffering(selected.code, { name: e.target.value })}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm font-medium"
              />
              <input
                type="text"
                aria-label="Offering code"
                value={selected.code}
                onChange={(e) => updateOffering(selected.code, { code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '') })}
                maxLength={6}
                className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm font-mono"
              />
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-stone-400 uppercase">
                  <th className="text-left py-2 font-medium">Package</th>
                  <th className="text-left py-2 font-medium">Description</th>
                  <th className="text-right py-2 font-medium">Price (₹)</th>
                  <th className="text-right py-2 font-medium">Hours</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {Object.entries(selected.packages).map(([pkgKey, pkg]) => (
                  <tr key={pkgKey}>
                    <td className="py-2 pr-2">
                      <input
                        type="text"
                        aria-label={`Package name ${pkgKey}`}
                        defaultValue={prettify(pkgKey)}
                        onBlur={(e) => renamePackage(selected.code, pkgKey, e.target.value)}
                        className="w-full rounded-md border border-transparent hover:border-stone-200 px-1 py-0.5 text-sm font-medium"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        type="text"
                        aria-label={`Description for ${prettify(pkgKey)}`}
                        value={pkg.description}
                        onChange={(e) => updatePackage(selected.code, pkgKey, { description: e.target.value })}
                        className="w-full rounded-md border border-transparent hover:border-stone-200 px-1 py-0.5 text-sm text-stone-600"
                      />
                    </td>
                    <td className="py-2 pr-2 text-right">
                      <input
                        type="number"
                        aria-label={`Price for ${prettify(pkgKey)}`}
                        value={pkg.base}
                        onChange={(e) => updatePackage(selected.code, pkgKey, { base: Number(e.target.value) || 0 })}
                        className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                      />
                    </td>
                    <td className="py-2 pr-2 text-right">
                      <input
                        type="number"
                        aria-label={`Hours for ${prettify(pkgKey)}`}
                        value={pkg.typical_hours ?? 0}
                        onChange={(e) => updatePackage(selected.code, pkgKey, { typical_hours: Number(e.target.value) || 0 })}
                        className="w-16 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                      />
                    </td>
                    <td className="py-2 text-right">
                      <button
                        onClick={() => deletePackage(selected.code, pkgKey)}
                        aria-label={`Delete ${prettify(pkgKey)}`}
                        className="text-stone-300 hover:text-red-500 text-sm"
                      >✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <button
              onClick={() => addPackage(selected.code)}
              className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900 mt-3"
            >
              + Add package
            </button>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/offerings-step.test.tsx`
Expected: PASS — 8 tests. The `beforeEach` confirm-mock at the top of the test file ensures the offering-delete path doesn't hit jsdom's missing `window.confirm`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/offerings-step.tsx \
        frontend/src/components/rate-card-wizard/__tests__/offerings-step.test.tsx
git commit -m "feat(rate-card): OfferingsStep (2a) — master/detail two-pane with editable code"
```

---

## Task 8: RateCardWizard composer

**Files:**
- Create: `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx`
- Create: `frontend/src/components/rate-card-wizard/index.ts`
- Create: `frontend/src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RateCardWizard } from '../rate-card-wizard'

describe('RateCardWizard', () => {
  beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true) })

  it('starts on sub-step 2a (Offerings)', () => {
    render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)
    expect(screen.getByText(/offerings & packages/i)).toBeInTheDocument()
  })

  it('advances through all 4 sub-steps and submits with default empty payload when all are skipped', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    // 2a → 2b
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/hourly rates by role/i)).toBeInTheDocument()

    // 2b → 2c
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/pricing multipliers/i)).toBeInTheDocument()

    // 2c → 2d
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/defaults & policies/i)).toBeInTheDocument()

    // 2d → submit
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith({
      version: 'v1',
      offerings: {},
      hourly_rates: {},
      multipliers: {},
      pass_through_markup: 0.10,
      standard_options: 3,
      standard_revisions: 2,
    })
  })

  it('navigates back and preserves prior sub-step state', async () => {
    const user = userEvent.setup()
    render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)

    // On 2a, add an offering
    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('New offering')

    // Advance to 2b
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/hourly rates by role/i)).toBeInTheDocument()

    // Back to 2a
    await user.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('New offering')
  })

  it('drops empty/invalid rows from the submitted payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    // 2a: add offering with empty packages — should be kept (offering has a name)
    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))

    // Advance through to submit with no other data
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      offerings: { O1: { name: 'New offering', code: 'O1', packages: {} } },
    }))
  })

  it('drops fixed-row multipliers with value 0 from the payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    // Skip to 2c (multipliers)
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))

    // Zero out rush job — others stay at their defaults
    const rushInput = screen.getByLabelText(/value for rush job/i)
    await user.clear(rushInput)
    await user.type(rushInput, '0')

    // Advance and submit
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    const payload = onSubmit.mock.calls[0][0]
    expect(payload.multipliers).not.toHaveProperty('urgency_rush')
    expect(payload.multipliers).toHaveProperty('annual_bundle')
    expect(payload.multipliers).toHaveProperty('existing_client')
    expect(payload.multipliers).toHaveProperty('complexity_enterprise')
  })

  it('disables the primary button while saving', () => {
    render(<RateCardWizard onSubmit={vi.fn()} saving={true} />)
    // Walk to last step is overkill — just check the button on 2a
    expect(screen.getByRole('button', { name: /save & continue/i })).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`
Expected: FAIL with module-not-found for `../rate-card-wizard`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx`:

```typescript
import { useState } from 'react'
import type { Offering, Multiplier } from '../../types/rate-card'
import { DEFAULT_PAYLOAD, type RateCardPayload } from './types'
import { WizardShell } from './wizard-shell'
import { OfferingsStep } from './offerings-step'
import { HourlyRatesStep } from './hourly-rates-step'
import { MultipliersStep } from './multipliers-step'
import { GlobalsStep, type GlobalsValue } from './globals-step'
import { KNOWN_MULTIPLIERS } from './known-multipliers'

interface Props {
  onSubmit: (data: RateCardPayload) => void
  saving: boolean
}

const STEPS = [
  { title: 'Offerings & Packages',  subtitle: "What you sell, and how it's packaged" },
  { title: 'Hourly rates by role',  subtitle: 'Used by the cost-model when proposals need time-based pricing' },
  { title: 'Pricing multipliers',   subtitle: 'Adjustments the cost-model applies automatically based on proposal context' },
  { title: 'Defaults & policies',   subtitle: 'Used as the baseline for every proposal — can be overridden per project' },
] as const

export function RateCardWizard({ onSubmit, saving }: Props) {
  const [subStep, setSubStep] = useState(0)
  const [offerings, setOfferings] = useState<Record<string, Offering>>({})
  const [hourlyRates, setHourlyRates] = useState<Record<string, number>>({})
  const [multipliers, setMultipliers] = useState<Record<string, Multiplier>>({})
  const [globals, setGlobals] = useState<GlobalsValue>({
    pass_through_markup: DEFAULT_PAYLOAD.pass_through_markup,
    standard_options:    DEFAULT_PAYLOAD.standard_options,
    standard_revisions:  DEFAULT_PAYLOAD.standard_revisions,
  })

  const isLast = subStep === STEPS.length - 1
  const continueLabel = isLast ? 'Finish rate card →' : 'Save & Continue →'

  const advance = () => setSubStep((s) => Math.min(s + 1, STEPS.length - 1))
  const goBack  = () => setSubStep((s) => Math.max(s - 1, 0))

  const handleContinue = () => {
    if (!isLast) {
      advance()
      return
    }
    onSubmit(filterPayload(offerings, hourlyRates, multipliers, globals))
  }

  return (
    <WizardShell
      subStep={subStep}
      total={STEPS.length}
      title={STEPS[subStep].title}
      subtitle={STEPS[subStep].subtitle}
      onBack={subStep > 0 ? goBack : undefined}
      onSkip={advance}
      onContinue={saving ? () => {} : handleContinue}
      continueLabel={continueLabel}
    >
      {/* Disabled state for the primary button comes via the saving prop */}
      <SavingShield saving={saving} />
      {subStep === 0 && <OfferingsStep    value={offerings}    onChange={setOfferings} />}
      {subStep === 1 && <HourlyRatesStep  value={hourlyRates}  onChange={setHourlyRates} />}
      {subStep === 2 && <MultipliersStep  value={multipliers}  onChange={setMultipliers} />}
      {subStep === 3 && <GlobalsStep      value={globals}      onChange={setGlobals} />}
    </WizardShell>
  )
}

/** Visually disables the WizardShell footer button when the parent is saving. */
function SavingShield({ saving }: { saving: boolean }) {
  if (!saving) return null
  return (
    <style>{`button[class*="bg-stone-900"]:not([aria-label]) { opacity: 0.5; pointer-events: none; }`}</style>
  )
}

function filterPayload(
  offerings: Record<string, Offering>,
  hourly_rates: Record<string, number>,
  multipliers: Record<string, Multiplier>,
  globals: GlobalsValue,
): RateCardPayload {
  // Offerings: keep if name is non-empty. Drop empty package rows within each.
  const cleanOfferings: Record<string, Offering> = {}
  for (const [code, off] of Object.entries(offerings)) {
    if (!off.name?.trim()) continue
    const cleanPackages: Record<string, typeof off.packages[string]> = {}
    for (const [k, pkg] of Object.entries(off.packages)) {
      if (pkg.base > 0 || pkg.description.trim()) cleanPackages[k] = pkg
    }
    cleanOfferings[code] = { ...off, packages: cleanPackages }
  }

  // Hourly rates: drop zero rates.
  const cleanRates: Record<string, number> = {}
  for (const [k, r] of Object.entries(hourly_rates)) {
    if (r > 0) cleanRates[k] = r
  }

  // Multipliers: drop any with value <= 0; merge defaults for known keys
  // the user left untouched (so the cost-model sees their canonical values).
  const cleanMults: Record<string, Multiplier> = {}
  for (const known of KNOWN_MULTIPLIERS) {
    const editing = multipliers[known.key]
    const value = editing?.value ?? known.defaultValue
    if (value > 0) {
      cleanMults[known.key] = { value, description: editing?.description ?? '' }
    }
  }
  for (const [k, m] of Object.entries(multipliers)) {
    if (KNOWN_MULTIPLIERS.some((kn) => kn.key === k)) continue
    if (m.value > 0) cleanMults[k] = m
  }

  return {
    version: DEFAULT_PAYLOAD.version,
    offerings: cleanOfferings,
    hourly_rates: cleanRates,
    multipliers: cleanMults,
    ...globals,
  }
}
```

Create `frontend/src/components/rate-card-wizard/index.ts`:

```typescript
export { RateCardWizard } from './rate-card-wizard'
export type { RateCardPayload } from './types'
```

Now update `WizardShell` to support `disabled`-style behavior on the primary button. The simplest fix is to add a `disabled` prop to `WizardShell` and pass `saving` through.

Modify `frontend/src/components/rate-card-wizard/wizard-shell.tsx` (Task 3 file). Replace the `Props` interface:

```typescript
interface Props {
  subStep: number
  total: number
  title: string
  subtitle: string
  children: ReactNode
  onBack?: () => void
  onSkip: () => void
  onContinue: () => void
  continueLabel?: string
  notice?: string
  disabled?: boolean
}
```

Replace the primary button at the bottom:

```typescript
<button
  onClick={onContinue}
  disabled={disabled}
  className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-stone-800 disabled:opacity-50 disabled:pointer-events-none"
>
  {continueLabel}
</button>
```

And in `rate-card-wizard.tsx`, replace the `SavingShield` and the `<WizardShell>` invocation:

```typescript
return (
  <WizardShell
    subStep={subStep}
    total={STEPS.length}
    title={STEPS[subStep].title}
    subtitle={STEPS[subStep].subtitle}
    onBack={subStep > 0 ? goBack : undefined}
    onSkip={advance}
    onContinue={handleContinue}
    continueLabel={continueLabel}
    disabled={saving}
  >
    {subStep === 0 && <OfferingsStep    value={offerings}    onChange={setOfferings} />}
    {subStep === 1 && <HourlyRatesStep  value={hourlyRates}  onChange={setHourlyRates} />}
    {subStep === 2 && <MultipliersStep  value={multipliers}  onChange={setMultipliers} />}
    {subStep === 3 && <GlobalsStep      value={globals}      onChange={setGlobals} />}
  </WizardShell>
)
```

And delete the `SavingShield` function entirely.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx`
Expected: PASS — 6 wizard tests + 8 shell tests = 14 tests.

If `wizard-shell.test.tsx` regresses on the disabled-button change, add this assertion to it:

```typescript
it('disables the primary button when disabled prop is true', () => {
  setup({ disabled: true })
  expect(screen.getByRole('button', { name: /save & continue/i })).toBeDisabled()
})
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rate-card-wizard/rate-card-wizard.tsx \
        frontend/src/components/rate-card-wizard/index.ts \
        frontend/src/components/rate-card-wizard/wizard-shell.tsx \
        frontend/src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx \
        frontend/src/components/rate-card-wizard/__tests__/wizard-shell.test.tsx
git commit -m "feat(rate-card): RateCardWizard composer with payload filtering"
```

---

## Task 9: Rewrite step-rate-card.tsx as a thin composer

**Files:**
- Modify: `frontend/src/pages/onboarding/step-rate-card.tsx` (full rewrite — was 107 LOC JSON paste)
- Create: `frontend/src/pages/onboarding/__tests__/step-rate-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/onboarding/__tests__/step-rate-card.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StepRateCard } from '../step-rate-card'

describe('StepRateCard (onboarding step 2)', () => {
  beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true) })

  it('renders the rate-card wizard, not a JSON textarea', () => {
    render(<StepRateCard onSubmit={vi.fn()} saving={false} />)
    // No JSON textarea
    expect(screen.queryByPlaceholderText(/version/i)).not.toBeInTheDocument()
    // Wizard chrome is present
    expect(screen.getByText(/offerings & packages/i)).toBeInTheDocument()
  })

  it('forwards the submitted payload through onSubmit when the user skips every sub-step', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<StepRateCard onSubmit={onSubmit} saving={false} />)
    // Skip 4 times
    for (let i = 0; i < 3; i++) {
      await user.click(screen.getByRole('button', { name: /save & continue/i }))
    }
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      version: 'v1',
      offerings: {},
      hourly_rates: {},
      pass_through_markup: 0.10,
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/pages/onboarding/__tests__/step-rate-card.test.tsx`
Expected: FAIL — current `step-rate-card.tsx` renders a textarea with placeholder JSON, so the assertion `queryByPlaceholderText(/version/i)` will FIND a textarea (test fails on that line) or the wizard text won't be found.

- [ ] **Step 3: Rewrite the page component**

Replace the entire contents of `frontend/src/pages/onboarding/step-rate-card.tsx` with:

```typescript
import { RateCardWizard, type RateCardPayload } from '../../components/rate-card-wizard'

interface Props {
  onSubmit: (data: RateCardPayload) => void
  saving: boolean
}

export function StepRateCard({ onSubmit, saving }: Props) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        Set up your rate card in 4 short steps. You can skip any section and finish it later in Settings.
      </p>
      <RateCardWizard onSubmit={onSubmit} saving={saving} />
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run src/pages/onboarding/__tests__/step-rate-card.test.tsx`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/onboarding/step-rate-card.tsx \
        frontend/src/pages/onboarding/__tests__/step-rate-card.test.tsx
git commit -m "feat(onboarding): rewrite step 2 as a thin RateCardWizard composer"
```

---

## Task 10: Full test sweep, build, lint

**Files:** None modified. This task is verification only.

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd frontend && pnpm test`
Expected: PASS — total count = previous baseline (131) + 8 new files (~40 new tests). Concretely you should see the new test files in the output and zero failures.

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && pnpm build`
Expected: clean build with no TS errors. `dist/` is regenerated.

- [ ] **Step 3: Lint**

Run: `cd frontend && pnpm lint`
Expected: no errors. If ESLint warns about unused imports or `any` usage in any of the new files, fix and re-commit.

- [ ] **Step 4: Manual smoke test (optional but recommended)**

If a dev server is convenient:
```bash
cd frontend && pnpm dev
# Open http://localhost:5173, register a new test account (use @example.com — .local TLD is rejected),
# advance to step 2, walk through the 4 sub-steps. Verify:
#  - Progress dots highlight correctly
#  - "+ Add offering" creates O1 and selects it; the right pane shows name/code inputs
#  - Common-role chips disappear after click and the row appears in the table
#  - All 4 multiplier rows render with defaults; the key in mono is visible
#  - Globals shows 10% / 3 / 2 by default and all are editable
#  - Finishing the wizard advances to onboarding step 3
```

- [ ] **Step 5: Final commit (only if there were follow-up fixes from steps 1-4)**

If steps 1-3 surfaced anything (lint warnings, type drift, missed test mock):

```bash
git add <fixed files>
git commit -m "fix(rate-card): <one-line description of the follow-up>"
```

If everything passed clean, no commit is needed — Task 9 was the final functional commit.

---

## Acceptance Recap

Verify against the spec's acceptance criteria (`docs/superpowers/specs/2026-05-18-rate-card-form-design.md`, section "Acceptance criteria"):

- ✓ `step-rate-card.tsx` no longer contains the JSON textarea or `PLACEHOLDER` constant (Task 9)
- ✓ `frontend/src/components/rate-card-wizard/` contains the 5 sub-step components + WizardShell + constants (Tasks 1–7)
- ✓ Walking through onboarding produces 4 sub-step screens in order (Task 10 manual smoke)
- ✓ All 4 sub-steps can be skipped; final submit produces a valid payload (Task 8 test: "advances through all 4 sub-steps and submits with default empty payload")
- ✓ Filling all 4 sub-steps and clicking Finish produces a payload with the same shape as the JSON paste (Task 8 test: "drops empty/invalid rows")
- ✓ `pnpm test --run` includes the new tests and they pass (Task 10 step 1)
- ✓ `pnpm build` is clean (Task 10 step 2)

## Deferred from spec (follow-up)

The spec describes a **timed yellow "fill this in later" notice** that should appear above the footer for ~2s before the wizard advances when the user skips or finishes an empty/invalid sub-step. This plan implements the underlying soft-required behavior (Save & Continue always advances) but does NOT implement the timed notice — the `WizardShell` `notice` prop exists but is never set by `RateCardWizard`.

This is a polish feature, not a correctness one. If we want to ship it after Task 10, the implementation is:

1. Add `noticeText: string | null` state to `RateCardWizard`
2. In `handleContinue`/`onSkip`, before calling `advance()`, check if the current sub-step's value is "empty" (length-0 object / 0 multipliers above threshold) — if so, `setNoticeText(...)` and use `setTimeout(() => { setNoticeText(null); advance() }, 1500)` instead of advancing immediately
3. Pass `noticeText ?? undefined` to `<WizardShell notice={...}>`
4. Add a wizard test that asserts the notice appears + auto-clears + advances

This adds ~30 LOC and 2 test cases. Skip for v1 unless usability feedback says otherwise.
