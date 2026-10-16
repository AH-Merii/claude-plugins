import type { On, RenderSurface } from 'claude-code'
import { type Engine, expect, mock, test } from 'claude-code/testing'

const HOME = '/home/ada'
const CONFIG = `${HOME}/.claude/attention.json`

// Stands in for the files the mod reads: only its config.
function files(on: On, contents: Record<string, string>) {
  on('fs.exists', (_$, e) => ({ value: e.path in contents }))
  on('fs.read', (_$, e) => ({ value: contents[e.path] ?? '' }))
}

// Stands in for Claude Code's own drawing of a reply, so what the mod hands on can be read back.
function engineDraws(on: On) {
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{`engine: ${e.props.text}`}</Text>
  })
}

// Nothing beneath the plugins answers these in a test; the engine's own part of each is not under test.
function engineEnds(on: On) {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  // With nothing pinned the band is left to Claude Code, which draws nothing there.
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })
}

function start($: Engine) {
  return $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true } as never)
}

function compose($: Engine, surfaces: RenderSurface[]) {
  const model = 'claude-haiku'
  return $.prompt.compose({ model, promptModel: model, surfaces, tools: [], outputStyle: null, traits: [] })
}

function finish($: Engine, answer: string, agentId?: string) {
  return $.turn.complete({
    answer,
    durationMs: 1000,
    isAborted: false,
    turnId: `t-${answer.length}`,
    reason: 'answer',
    ...(agentId ? { agentId } : {}),
  } as never)
}

function reply($: Engine, text: string) {
  return $.ui.mount({
    plugin: 'attention',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text, isFirstOfReply: true },
  })
}

function band($: Engine) {
  return $.ui.mount({
    plugin: 'attention',
    surface: 'terminal',
    component: 'AbovePrompt',
    requestId: 'band',
    props: { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 100 } as never,
  })
}

// The open items the band shows, by id.
async function pinned($: Engine) {
  const ui = await band($)
  const ids = (await ui.findAll({ type: 'Text', text: /^ D\d+ $/ })).map(t => String(t.text).trim())
  await ui.unmount()
  return ids
}

test('Claude is told the tags only where a terminal draws them, configured categories included', async ($, on) => {
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'You are Claude Code.', scope: 'shared' }] }))
  mock.env(on, { HOME })
  files(on, {
    [CONFIG]: JSON.stringify({
      categories: { 'ci-red': { label: 'CI', color: 'red', meaning: 'a failed check' }, optional: { enabled: false } },
    }),
  })

  const inTerminal = await compose($, ['terminal'])
  const elsewhere = await compose($, ['desktop'])
  const told = inTerminal.sections.find(s => s.id === 'attention:tags')?.text ?? ''

  expect(elsewhere.sections.map(s => s.id)).toEqual(['intro'])
  expect(inTerminal.sections.map(s => s.id)).toEqual(['intro', 'attention:tags'])
  for (const tag of ['must-know', 'decide-now', 'decide-later', 'default', 'your-action', 'ci-red']) {
    expect(told).toContain(`\`${tag}\`: `)
  }
  expect(told).not.toContain('`optional`')
})

test('a config the mod cannot read is named in a toast, once, and the defaults apply', async ($, on) => {
  mock.env(on, { HOME })
  files(on, { [CONFIG]: '{ "categories": ' })
  const toasts: string[] = []
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('prompt.compose', () => ({ sections: [] }))
  engineEnds(on)

  await start($)
  const { sections } = await compose($, ['terminal'])

  expect(toasts).toEqual([expect.stringMatching(/attention\.json: not valid JSON/)])
  expect(sections[0]?.text).toContain('`decide-now`: ')
})

test('a reply with tagged lines hands the rest to Claude Code and draws each item under it with its label', async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineDraws(on)

  const ui = await reply(
    $,
    'Merged #72.\n\n> [!must-know] The wizard never ran live.\n> [!decide-now] D4: File both issues as drafted?',
  )
  const engine = await ui.findAll({ type: 'Text', text: /^engine: / })
  const labels = await ui.findAll({ type: 'Text', text: /MUST KNOW|DECIDE NOW/ })
  const items = await ui.findAll({ type: 'Text', text: /^(D4 )?(The wizard|File both)/ })
  await ui.unmount()

  expect(engine.map(t => t.text)).toEqual(['engine: Merged #72.'])
  expect(labels.map(t => [String(t.text).trim(), t.props.color])).toEqual([
    ['MUST KNOW', 'red'],
    ['DECIDE NOW', '#ff8700'],
  ])
  expect(items.map(t => t.text)).toEqual(['The wizard never ran live.', 'D4 File both issues as drafted?'])
})

test("a tinted item's text is drawn in a dimmer shade of its category's colour, with code spans bold in the full colour", async ($, on) => {
  mock.env(on, { HOME })
  files(on, {
    [CONFIG]: JSON.stringify({
      categories: { 'must-know': { tint: true, color: '#3366ff' }, 'your-action': { tint: false } },
    }),
  })
  engineEnds(on)
  engineDraws(on)
  await start($)

  const ui = await reply(
    $,
    '> [!must-know] Run `! rm -rf ~/.azure` before **D2**.\n> [!your-action] Sign in to the test account.',
  )
  const tinted = await ui.findAll({ type: 'Text', text: /^Run / })
  const code = await ui.findAll({ type: 'Text', text: /^! rm -rf ~\/\.azure$/ })
  const markdown = await ui.findAll({ type: 'Markdown' })
  await ui.unmount()

  expect(tinted.map(t => [t.text, t.props.color, t.props.dimColor])).toEqual([
    ['Run ! rm -rf ~/.azure before D2.', '#3061f2', undefined],
  ])
  expect(code.map(t => [t.props.bold, t.props.color])).toEqual([[true, '#3366ff']])
  expect(markdown.map(m => m.props.text)).toEqual(['Sign in to the test account.'])
})

test('a reply with no tagged lines is left to Claude Code', async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineDraws(on)
  const text = 'Merged #72.\n\n> A quote that tags nothing.'

  const ui = await reply($, text)
  const drawn = await ui.findAll({ type: 'Text', text: /^engine: / })
  await ui.unmount()

  expect(drawn.map(t => t.text)).toEqual([`engine: ${text}`])
})

test('decisions stay pinned above the prompt until Claude settles them; other items are not pinned', async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineEnds(on)

  await finish(
    $,
    [
      'Done.',
      '> [!decide-now] D1: Merge #41 as is?',
      '> [!decide-later] D2: Go past slice 15? (after D1)',
      '> [!default] D3: Classify only when asked.',
      '> [!must-know] The wizard never ran live.',
    ].join('\n'),
  )
  const first = await pinned($)
  await finish($, 'Merging.\n> [!resolved] D1: merge as is')
  const second = await pinned($)
  await finish($, 'Here is what D2 means.\n> [!decide-later] D2: Build slices 16 to 20 next?')
  const ui = await band($)
  const restated = await ui.findAll({ type: 'Text', text: /slices 16 to 20/ })
  await ui.unmount()

  expect(first).toEqual(['D1', 'D2'])
  expect(second).toEqual(['D2'])
  expect(restated).toHaveLength(1)
})

test("a subagent's report pins nothing", async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineEnds(on)

  await finish($, '> [!decide-now] D1: Merge #41 as is?', 'agent-7')

  expect(await pinned($)).toEqual([])
})

test('the user can dismiss a pinned item from the band', async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineEnds(on)
  await finish($, '> [!decide-now] D1: Merge #41 as is?\n> [!decide-now] D2: Close #49?')

  const ui = await band($)
  await ui.press({ key: 'attention:dismiss:D1' })
  await ui.unmount()

  expect(await pinned($)).toEqual(['D2'])
})

test('what the user types carries the open items to Claude; notifications and commands do not', async ($, on) => {
  mock.env(on, { HOME })
  files(on, {})
  engineEnds(on)
  const context: (readonly string[] | undefined)[] = []
  on('prompt.submit', (_$, e) => {
    context.push(e.context)
    return { text: e.text, context: e.context }
  })
  const submit = (text: string, kind: string) => $.prompt.submit({ text, wait: false, origin: { kind } } as never)

  await submit('hello', 'composer')
  await finish($, '> [!decide-now] D1: Merge #41 as is?')
  await submit('D1: what does cleanup involve?', 'composer')
  await submit('task finished', 'task-notification')
  await submit('/compact', 'composer')

  expect(context[0]).toBeUndefined()
  expect(context[1]).toEqual([expect.stringMatching(/D1 \[decide-now\] Merge #41 as is\?/)])
  expect(context.slice(2)).toEqual([undefined, undefined])
})
