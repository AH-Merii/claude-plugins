// A kind of thing to pay attention to, and how its lines are drawn.
export type Category = {
  id: string
  label: string
  // A theme key (`error`, `warning`, …) or a raw colour: a name such as `red`, or hex.
  color: string
  // What the item is, as Claude is told it.
  meaning: string
  // Kept in the band above the prompt until Claude marks it resolved.
  pin: boolean
  // Drawn dim: an item the reader may skip.
  dim: boolean
  // The item's text drawn in a dimmer shade of the category's colour; on unless a category turns it off.
  tint: boolean
}

// A pinned item still waiting on the user, with Claude's latest recommendation on it.
export type OpenItem = { id: string; tag: string; text: string; suggestion?: string }

declare module 'claude-code' {
  interface PluginState {
    attention: { categories: Category[]; open: OpenItem[] }
  }
}
