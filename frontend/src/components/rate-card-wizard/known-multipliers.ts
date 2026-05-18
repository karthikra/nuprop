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
