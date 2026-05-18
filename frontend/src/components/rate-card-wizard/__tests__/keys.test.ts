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
