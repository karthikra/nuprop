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
