import { RESOLVED } from './categories'

export type Item = { tag: string; id?: string; text: string }

// `> [!decide-now] D2: Merge as is?`: a blockquote led by a tag, with an optional id such as D2.
const ITEM = /^ {0,3}>\s?\[!([a-z][a-z0-9-]*)\]\s*(?:([A-Z]\d+)\s*[:—–-]\s*)?(.*)$/
// A blockquote line that carries on the item above it.
const MORE = /^ {0,3}>\s?(?!\s*\[!)(.*\S.*)$/
// A code fence, which may quote the syntax without meaning it.
const FENCE = /^ {0,3}(`{3,}|~{3,})/

// Takes the tagged lines out of a reply: the items, in the order written, and the text left without them.
// Tags outside `tags` (and `resolved`) are not this mod's, so they stay in the text.
export function parse(text: string, tags: ReadonlySet<string>): { items: Item[]; rest: string } {
  const items: Item[] = []
  const rest: string[] = []
  let fence: string | undefined
  let last: Item | undefined

  for (const line of text.split('\n')) {
    const open = FENCE.exec(line)?.[1]
    if (fence !== undefined) {
      if (open !== undefined && open[0] === fence[0] && open.length >= fence.length) fence = undefined
      rest.push(line)
      continue
    }
    if (open !== undefined) {
      fence = open
      last = undefined
      rest.push(line)
      continue
    }

    const item = ITEM.exec(line)
    const tag = item?.[1]
    if (item && tag !== undefined && (tags.has(tag) || tag === RESOLVED)) {
      last = { tag, ...(item[2] ? { id: item[2] } : {}), text: (item[3] ?? '').trim() }
      items.push(last)
      continue
    }
    const more = last && MORE.exec(line)
    if (last && more) {
      last.text = `${last.text} ${(more[1] ?? '').trim()}`.trim()
      continue
    }
    last = undefined
    rest.push(line)
  }
  return { items: items.filter(i => i.text !== '' || i.tag === RESOLVED), rest: rest.join('\n').trimEnd() }
}
