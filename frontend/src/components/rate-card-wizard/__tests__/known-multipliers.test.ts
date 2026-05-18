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
