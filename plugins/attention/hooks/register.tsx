import type { EngineInterface as Engine, Register } from 'claude-code'
import { atom, read, update } from 'claude-code'

import type { Category, OpenItem } from '../types'
import { type Config, configure, DEFAULTS, RESOLVED } from './categories'
import { type Item, parse } from './parse'
import { instructions, reminder } from './prompt'
import { shade } from './shade'

const categoriesState = atom({ plugin: 'attention', key: 'categories' } as const, [...DEFAULTS])
const openState = atom({ plugin: 'attention', key: 'open' } as const, [])

const CONFIG = 'attention.json'
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

// Reads the config into the session's state and names what in it can't be used.
async function refresh($: Engine) {
  const { path, categories, errors } = await load($)
  const current = await read($, categoriesState)
  if (JSON.stringify(current) !== JSON.stringify(categories)) {
    await update($, categoriesState, () => categories)
  }
  const report = errors.join('; ')
  if (report !== '' && report !== reported) {
    $.ui.toast(`attention: ${path}: ${report}`)
  }
  reported = report
  return categories
}

// Pinned items as of a reply: new and restated ones added or updated by id, settled ones dropped.
function track(open: readonly OpenItem[], items: readonly Item[], categories: readonly Category[]): OpenItem[] {
  const pinned = new Set(categories.filter(c => c.pin).map(c => c.id))
  const next = [...open]
  for (const item of items) {
    if (item.id === undefined) continue
    const at = next.findIndex(o => o.id === item.id)
    if (item.tag === RESOLVED) {
      if (at >= 0) next.splice(at, 1)
    } else if (pinned.has(item.tag)) {
      const entry = { id: item.id, tag: item.tag, text: item.text }
      if (at >= 0) next[at] = entry
      else next.push(entry)
    }
  }
  return next
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

  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined && e.answer !== '') {
      const categories = await read($, categoriesState)
      const { items } = parse(e.answer, new Set(categories.map(c => c.id)))
      if (items.some(i => i.id !== undefined)) {
        await update($, openState, open => track(open, items, categories))
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
            <Box width={GUTTER} flexShrink={0}>
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
                  {item.id && <Text color={category.color} bold>{`${item.id} `}</Text>}
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
                <Markdown text={item.id ? `**${item.id}** ${item.text}` : item.text} dimColor={category.dim} />
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
    const { Box, Button, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {open.map(o => {
          const category = categories.find(c => c.id === o.tag)
          const color = category?.color ?? 'text'
          return (
            <Box key={`attention:open:${o.id}`} flexDirection="row">
              <Text color={color}>▌</Text>
              <Text color={color} bold>{` ${o.id} `}</Text>
              <Box flexGrow={1} width={0}>
                <Text wrap="truncate-end">{plain(o.text)}</Text>
              </Box>
              <Button
                key={`attention:dismiss:${o.id}`}
                label=" ✕ "
                plain
                dimColor
                onPress={() => update($, openState, list => list.filter(x => x.id !== o.id))}
              />
            </Box>
          )
        })}
      </Box>
    )
  })
}
