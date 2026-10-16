import type { EngineInterface as Engine, Register } from 'claude-code'
import { atom, read, update } from 'claude-code'

import type { Category, OpenItem } from '../types'
import { type Config, configure, DEFAULTS, RESOLVED, SUGGEST } from './categories'
import { type Item, parse } from './parse'
import { instructions, reminder } from './prompt'
import { shade } from './shade'

const categoriesState = atom({ plugin: 'attention-is-all-i-need', key: 'categories' } as const, [...DEFAULTS])
const openState = atom({ plugin: 'attention-is-all-i-need', key: 'open' } as const, [])

const CONFIG = 'attention-is-all-i-need.json'
// The jump button's label: nf-md-magnify when the nerd-font mod says the terminal has a Nerd Font, else the emoji.
const MAGNIFY = '\u{F0349}'
const PLAIN_MAGNIFY = '🔍'
// nerd-font's answer: true, false, or undefined until its check has run. Only true means glyphs.
const nerdFont = { plugin: 'nerd-font', key: 'enabled' } as const
// The reply's left gutter, as Claude Code draws it: the bullet on a reply's first block, else blank.
const GUTTER = 2
// How a settled item is drawn: a green label, its text a dimmer green, since it only confirms what the user said.
const SETTLED: Category = {
  id: RESOLVED,
  label: 'SETTLED',
  color: 'green',
  meaning: '',
  pin: false,
  dim: false,
  tint: true,
}

// The config file sits beside Claude Code's own settings.
async function configPath($: Engine) {
  const dir = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await $.env.get('HOME')}/.claude`
  return `${dir.replace(/\/+$/, '')}/${CONFIG}`
}

async function load($: Engine): Promise<Config & { path: string }> {
  const path = await configPath($)
  if (!(await $.fs.exists(path))) {
    return { path, ...configure(undefined) }
  }
  let raw: unknown
  try {
    raw = JSON.parse(await $.fs.read(path))
  } catch {
    return { path, ...configure(undefined), errors: ['not valid JSON; using the defaults'] }
  }
  return { path, ...configure(raw) }
}

// The config's errors last reported, so a broken file is named once, not on every request.
let reported = ''

// Where each item id was first written this turn: the message id of the reply block that holds it. A reply's
// blocks are stored as the turn goes, before turn.complete, which carries no message ids.
let raisedIn = new Map<string, string>()

// Reads the config into the session's state and names what in it can't be used.
async function refresh($: Engine) {
  const { path, categories, errors } = await load($)
  const current = await read($, categoriesState)
  if (JSON.stringify(current) !== JSON.stringify(categories)) {
    await update($, categoriesState, () => categories)
  }
  const report = errors.join('; ')
  if (report !== '' && report !== reported) {
    $.ui.toast(`attention-is-all-i-need: ${path}: ${report}`)
  }
  reported = report
  return categories
}

// Pinned items as of a reply: new and restated ones added or updated by id, settled ones dropped, and each
// suggestion attached to the open decision it names.
function track(
  open: readonly OpenItem[],
  items: readonly Item[],
  categories: readonly Category[],
  raised: ReadonlyMap<string, string>,
): OpenItem[] {
  const pinned = new Set(categories.filter(c => c.pin).map(c => c.id))
  const next = [...open]
  for (const item of items) {
    if (item.id === undefined || item.tag === SUGGEST) continue
    const at = next.findIndex(o => o.id === item.id)
    if (item.tag === RESOLVED) {
      if (at >= 0) next.splice(at, 1)
    } else if (pinned.has(item.tag)) {
      const entry = { id: item.id, tag: item.tag, text: item.text }
      // A restatement keeps where the item was first raised.
      if (at >= 0) next[at] = { ...next[at], ...entry }
      else next.push({ ...entry, from: raised.get(item.id) })
    }
  }
  // After the decisions, so a suggestion finds one raised in the same reply wherever it sits.
  for (const item of items) {
    const at = item.tag === SUGGEST ? next.findIndex(o => o.id === item.id) : -1
    const decision = next[at]
    if (decision) next[at] = { ...decision, suggestion: item.text }
  }
  return next
}

// The id an item is drawn with: a suggestion's is its decision's, marked S.
function shownId(item: Item) {
  return item.id && (item.tag === SUGGEST ? `${item.id}S` : item.id)
}

// An item's text as Text can draw it: code spans kept apart so they can stand out, emphasis marks dropped.
function spans(text: string) {
  return text
    .replace(/\*\*([^*]*)\*\*/g, '$1')
    .split(/(`[^`]*`)/)
    .filter(part => part !== '')
    .map(part =>
      part.startsWith('`') && part.endsWith('`')
        ? { text: part.slice(1, -1), isCode: true }
        : { text: part, isCode: false },
    )
}

// Markdown a one-line Text can't draw: code spans and emphasis lose their marks.
function plain(text: string) {
  return text.replace(/`([^`]*)`/g, '$1').replace(/\*\*([^*]*)\*\*/g, '$1')
}

// Scrolls the transcript to the reply that first raised an item, its top at the top of the screen; says so when
// that reply is gone, as after a rewind summarizes it away. The item stays pinned either way.
async function jump($: Engine, id: string) {
  const from = (await read($, openState)).find(o => o.id === id)?.from
  const { deny } =
    from === undefined
      ? { deny: 'not recorded' }
      : await $.ui.scroll({ to: { requestId: from }, block: 'start' }).catch((err: unknown) => ({ deny: String(err) }))
  if (deny !== undefined) {
    $.ui.toast(`attention-is-all-i-need: the reply that raised ${id} is no longer in the transcript (${deny})`)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await refresh($)
    return next(e)
  })

  // Only where a terminal draws the replies: elsewhere the tags would reach the reader as raw text.
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    if (!e.surfaces.includes('terminal')) {
      return composed
    }
    const categories = await refresh($)
    return {
      sections: [...composed.sections, { id: 'attention:tags', text: instructions(categories), scope: 'session' }],
    }
  })

  on('prompt.submit', async ($, e, next) => {
    const open = await read($, openState)
    // Only beside what the user typed: a slash command, a notification or a peer's message settles nothing.
    if (e.origin.kind !== 'composer' || e.text.startsWith('/') || open.length === 0) {
      return next(e)
    }
    return next({ ...e, context: [...(e.context ?? []), reminder(open)] })
  })

  on('session.append', { door: 'response' }, async ($, e, next) => {
    if (e.agentId === undefined) {
      const text = e.message.content.map(block => (block.type === 'text' ? block.text : '')).join('\n')
      const categories = await read($, categoriesState)
      for (const { id } of parse(text, new Set(categories.map(c => c.id))).items) {
        if (id !== undefined && !raisedIn.has(id)) raisedIn.set(id, e.uuid)
      }
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined) {
      const raised = raisedIn
      raisedIn = new Map()
      const categories = await read($, categoriesState)
      const { items } = parse(e.answer, new Set(categories.map(c => c.id)))
      if (items.some(i => i.id !== undefined)) {
        await update($, openState, open => track(open, items, categories, raised))
      }
    }
    return next(e)
  })

  on('ui.render', { component: 'AssistantMessage', surface: 'terminal' }, async ($, e, next) => {
    const categories = await read($, categoriesState)
    const { items, rest } = parse(e.props.text, new Set(categories.map(c => c.id)))
    if (items.length === 0) {
      return next(e)
    }

    const { Box, Markdown, Text } = $.ui.resolve(e)
    const body = rest.trim() === '' ? undefined : await next({ ...e, props: { ...e.props, text: rest } })
    const styled = items.map(item => ({ item, category: categories.find(c => c.id === item.tag) ?? SETTLED }))
    const width = Math.max(...styled.map(s => s.category.label.length))

    return (
      <Box flexDirection="column">
        {body}
        {styled.map(({ item, category }, i) => (
          <Box key={`${e.requestId}:attention:${i}`} flexDirection="row" marginTop={i === 0 && body ? 1 : 0}>
            <Box width={e.props.isFirstOfReply ? GUTTER : 0} flexShrink={0}>
              {i === 0 && !body && e.props.isFirstOfReply && <Text color="text">●</Text>}
            </Box>
            <Box flexShrink={0}>
              <Text color={category.color} dimColor={category.dim}>
                ▌
              </Text>
              <Text color={category.color} dimColor={category.dim} bold>
                {` ${category.label.padEnd(width)} `}
              </Text>
            </Box>
            <Box flexGrow={1} width={0}>
              {category.tint ? (
                // Markdown takes no colour, so a tinted item is drawn as Text in a shade of its category's colour.
                <Text {...(shade(category.color) ? { color: shade(category.color) } : { dimColor: true })}>
                  {item.id && <Text color={category.color} bold>{`${shownId(item)} `}</Text>}
                  {spans(item.text).map(s =>
                    s.isCode ? (
                      <Text color={category.color} bold>
                        {s.text}
                      </Text>
                    ) : (
                      s.text
                    ),
                  )}
                </Text>
              ) : (
                <Markdown text={item.id ? `**${shownId(item)}** ${item.text}` : item.text} dimColor={category.dim} />
              )}
            </Box>
          </Box>
        ))}
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt', surface: 'terminal' }, async ($, e, next) => {
    const open = await read($, openState)
    if (e.props.hasSurvey || open.length === 0) {
      return next(e)
    }
    const categories = await read($, categoriesState)
    const suggest = categories.find(c => c.id === SUGGEST)
    // Read while drawing, so the band redraws when nerd-font answers or its setting changes.
    const { value: hasNerdFont } = await $.state.get(nerdFont)
    const magnify = hasNerdFont === true ? MAGNIFY : PLAIN_MAGNIFY
    const { Box, Button, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {open.map(o => {
          const color = categories.find(c => c.id === o.tag)?.color ?? 'text'
          return (
            <Box key={`attention:open:${o.id}`} flexDirection="column">
              <Box flexDirection="row">
                <Text color={color}>▌</Text>
                <Text color={color} bold>{` ${o.id} `}</Text>
                <Box flexGrow={1} width={0}>
                  <Text wrap="truncate-end">{plain(o.text)}</Text>
                </Box>
                <Button
                  key={`attention:jump:${o.id}`}
                  label={` ${magnify} `}
                  plain
                  dimColor
                  onPress={() => jump($, o.id)}
                />
                <Button
                  key={`attention:dismiss:${o.id}`}
                  label=" ✕ "
                  plain
                  dimColor
                  onPress={() => update($, openState, list => list.filter(x => x.id !== o.id))}
                />
              </Box>
              {suggest && o.suggestion !== undefined && (
                <Box flexDirection="row">
                  <Text color={suggest.color}>▌</Text>
                  <Text color={suggest.color} bold>{` ${o.id}S `}</Text>
                  <Box flexGrow={1} width={0}>
                    <Text wrap="truncate-end" {...(shade(suggest.color) ? { color: shade(suggest.color) } : {})}>
                      {plain(o.suggestion)}
                    </Text>
                  </Box>
                </Box>
              )}
            </Box>
          )
        })}
      </Box>
    )
  })
}
