import type { Category } from '../types'

// The defaults come from an audit of 14 sessions of skimmed replies: what got missed, and what it cost.
export const DEFAULTS: readonly Category[] = [
  {
    id: 'must-know',
    label: 'MUST KNOW',
    color: 'red',
    meaning:
      'something the user must read before going on: a risk, a surprising finding, a change you made that they ' +
      'did not ask for, or work you skipped, could not verify or that failed',
    pin: false,
    dim: false,
    tint: true,
  },
  {
    id: 'decide-now',
    label: 'DECIDE NOW',
    color: '#ff8700',
    meaning: 'a choice you need from the user before you can finish the current task',
    pin: true,
    dim: false,
    tint: true,
  },
  {
    id: 'decide-later',
    label: 'DECIDE LATER',
    color: 'yellow',
    meaning: 'a choice a later task needs; you can carry on without it for now',
    pin: true,
    dim: false,
    tint: true,
  },
  {
    id: 'suggestion',
    label: 'SUGGESTION',
    color: 'cyan',
    meaning:
      'your recommendation on a decision still open, under the id of that decision (`D6: …`); whenever the reply ' +
      'weighs in on an open decision, the recommendation goes here as well as in the prose',
    pin: false,
    dim: false,
    tint: true,
  },
  {
    id: 'proceeding-with',
    label: 'PROCEEDING WITH',
    color: 'magenta',
    meaning: 'a choice you made yourself and are acting on; say what you chose and the words that overrule it',
    pin: false,
    dim: false,
    tint: true,
  },
  {
    id: 'your-action',
    label: 'YOUR ACTION',
    color: 'cyan',
    meaning: 'something only the user can do: run a command, sign in, restart something, check something on screen',
    pin: false,
    dim: false,
    tint: true,
  },
  {
    id: 'optional',
    label: 'OPTIONAL',
    color: 'inactive',
    meaning: 'an offer or a nice-to-know the user can safely skip',
    pin: false,
    dim: true,
    tint: true,
  },
]

// The tag that closes a pinned item; not a category of its own.
export const RESOLVED = 'resolved'
// The category whose items attach to a pinned decision, by its id, instead of standing alone.
export const SUGGEST = 'suggestion'
// Ids the categories had before they were renamed, so an older attention-is-all-i-need.json still reaches them.
const RENAMED: Record<string, string> = { suggest: 'suggestion', default: 'proceeding-with' }

const ID = /^[a-z][a-z0-9-]*$/
const FIELDS = ['label', 'color', 'meaning', 'pin', 'dim', 'tint', 'enabled'] as const

export type Config = { categories: Category[]; errors: string[] }

// Lays the user's config over the defaults. Each key of `categories` is a category id: a default's id changes
// only the fields given, `"enabled": false` drops it, and a new id adds a category, which needs a label, a colour
// and a meaning. What can't be read is reported and left out, so one bad entry never costs the rest.
export function configure(raw: unknown): Config {
  const errors: string[] = []
  const categories = DEFAULTS.map(c => ({ ...c }))
  if (raw === undefined) {
    return { categories, errors }
  }
  const overrides = isObject(raw) ? raw.categories : undefined
  if (!isObject(raw) || (overrides !== undefined && !isObject(overrides))) {
    return { categories, errors: ['expected {"categories": {"<id>": {...}}}; using the defaults'] }
  }

  const dropped = new Set<string>()
  for (const [key, entry] of Object.entries(overrides ?? {})) {
    const id = RENAMED[key] ?? key
    const error = check(id, entry, categories)
    if (error !== undefined) {
      errors.push(`${key}: ${error}`)
      continue
    }
    const fields = entry as Partial<Category> & { enabled?: boolean }
    if (fields.enabled === false) {
      dropped.add(id)
      continue
    }
    const known = categories.find(c => c.id === id)
    const { enabled: _, ...rest } = fields
    if (known) {
      Object.assign(known, rest)
    } else {
      categories.push({
        id,
        pin: false,
        dim: false,
        tint: true,
        ...(rest as Omit<Category, 'id' | 'pin' | 'dim' | 'tint'>),
      })
    }
  }
  return { categories: categories.filter(c => !dropped.has(c.id)), errors }
}

function check(id: string, entry: unknown, categories: Category[]): string | undefined {
  if (!ID.test(id) || id === RESOLVED) {
    return `an id is lowercase letters, digits and dashes, and "${RESOLVED}" is taken`
  }
  if (!isObject(entry)) {
    return 'expected an object'
  }
  const unknown = Object.keys(entry).filter(k => !(FIELDS as readonly string[]).includes(k))
  if (unknown.length > 0) {
    return `unknown field ${unknown.map(k => `"${k}"`).join(', ')}; the fields are ${FIELDS.join(', ')}`
  }
  for (const key of ['label', 'color', 'meaning'] as const) {
    if (key in entry && (typeof entry[key] !== 'string' || entry[key].trim() === '')) {
      return `"${key}" must be a non-empty string`
    }
  }
  for (const key of ['pin', 'dim', 'tint', 'enabled'] as const) {
    if (key in entry && typeof entry[key] !== 'boolean') {
      return `"${key}" must be true or false`
    }
  }
  const isNew = !categories.some(c => c.id === id)
  const missing = (['label', 'color', 'meaning'] as const).filter(k => !(k in entry))
  if (isNew && entry.enabled !== false && missing.length > 0) {
    return `a new category needs ${missing.map(k => `"${k}"`).join(', ')}`
  }
  return undefined
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
