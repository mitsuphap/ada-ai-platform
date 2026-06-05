/**
 * Format an arbitrary database cell value into a human-readable string for table display.
 */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'

  if (Array.isArray(value)) {
    return value.length ? value.map((v) => formatValue(v)).join(', ') : '—'
  }

  if (typeof value === 'boolean') return value ? 'Yes' : 'No'

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }

  return String(value)
}
