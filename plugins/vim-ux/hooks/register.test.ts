import type { On } from 'claude-code'
import { type Engine, expect, test } from 'claude-code/testing'

// DECSCUSR, steady shapes: the user's choice (handoffs/vim-ux.md, "Open decisions").
const BAR = '\x1b[6 q'
const BLOCK = '\x1b[2 q'
const DEFAULT = '\x1b[0 q'

// The PromptHint line as Claude Code draws it in each vim mode; NORMAL shows no label.
const INSERT = '-- INSERT --'
const NORMAL = ''
const VISUAL = '-- VISUAL --'

// `hint` is the whole line, pills and shortcuts hint included (PromptHint in the types), as in
// the live run: '-- INSERT -- ⏸ manual mode on', then '⏸ manual mode on' after Esc
// (~/.config/claude/mod-research/vim-ux/v1-insert.png, v2-normal-after-esc.png).
const PILL = '⏸ manual mode on'

type Settings = Record<string, unknown>
type Write = { path: string; text: string }

const tty = (...texts: string[]): Write[] => texts.map(text => ({ path: '/dev/tty', text }))

// The hint line as Claude Code draws it beneath the mod.
const hintLine = (hint: string) => ({ type: 'Text' as const, props: {}, children: [hint] })

const VIM: Settings = { editorMode: 'vim' }
// statusLine.hideVimModeIndicator: Claude Code then leaves the `-- INSERT --` / `-- VISUAL --`
// label out of the hint line for the status line to show (its settings schema, 2.1.289).
const labelHidden = (hideVimModeIndicator: boolean): Settings => ({
  editorMode: 'vim',
  statusLine: { type: 'command', command: 'x', hideVimModeIndicator },
})
const HIDDEN_LABEL = labelHidden(true)

// Stands in for Claude Code beneath the mod: answers what it would, and records what
// the mod sends out. `settings.current` is what settings.json holds at each read.
function claudeCode(on: On, settings: { current: Settings } = { current: VIM }) {
  const sent = {
    writes: [] as Write[],
    fills: [] as { text: string; mode: string | undefined }[],
    registered: [] as unknown[],
    invalidated: [] as unknown[],
    aborted: [] as string[],
  }
  on('settings.read', () => ({ value: settings.current }))
  on('fs.write', (_$, e) => {
    sent.writes.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('prompt.fill', (_$, e) => {
    sent.fills.push({ text: e.text, mode: e.mode })
    return { isFilled: true }
  })
  on('command.register', (_$, e) => {
    sent.registered.push(e)
    return { value: { command: e.name } }
  })
  on('ui.invalidate', (_$, e) => {
    sent.invalidated.push(e)
    return { value: undefined }
  })
  on('turn.abort', (_$, e) => {
    sent.aborted.push(e.turnId)
    return { value: undefined }
  })
  on('ui.render', { component: 'PromptHint' }, (_$, e) => hintLine(e.props.hint))
  on('ui.render', () => ({ type: 'Text', props: {}, children: [] }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.end', (_$, e) => ({ sessionId: e.sessionId }))
  on('turn.start', (_$, e) => ({ turnId: e.turnId }))
  on('command.run', () => ({ text: 'Claude Code ran it' }))
  on('command.describe', (_$, e) => ({ description: e.description, isHidden: e.isHidden }))
  return sent
}

const start = ($: Engine) => $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })

type EndReason = 'clear' | 'resume' | 'logout' | 'prompt_input_exit' | 'other'
const end = ($: Engine, reason: EndReason) => $.session.end({ reason, sessionId: 's', resume: { id: 's' } })

const mountHint = ($: Engine, hint: string) =>
  $.ui.mount({ plugin: 'vim-ux', surface: 'terminal', component: 'PromptHint', props: hintProps(hint) })
const hintProps = (hint: string) => ({ hint, isDraft: false, isWorking: false })

// Draws the prompt hint as Claude Code does, first in `hint`, then in each of `then`,
// and returns what the hint line showed each time.
async function showModes($: Engine, hint: string, ...then: string[]) {
  const ui = await mountHint($, hint)
  const shown = [await ui.drawn()]
  for (const next of then) {
    await ui.redraw(hintProps(next))
    shown.push(await ui.drawn())
  }
  await ui.unmount()
  return shown
}

const clearCommand = ($: Engine) =>
  $.command.run({
    command: 'vim-ux-clear',
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 80 },
  })

for (const [mode, hint, shape, name] of [
  ['INSERT', INSERT, BAR, 'bar'],
  ['INSERT', `${INSERT} ${PILL}`, BAR, 'bar'],
  ['NORMAL', NORMAL, BLOCK, 'block'],
  ['NORMAL', PILL, BLOCK, 'block'],
  ['NORMAL', '? for shortcuts', BLOCK, 'block'],
  ['VISUAL', VISUAL, BLOCK, 'block'],
  ['VISUAL', `${VISUAL} ${PILL}`, BLOCK, 'block'],
] as const) {
  test(`the cursor is a ${name} in ${mode}, and the hint line shows as before (hint '${hint}')`, async ($, on) => {
    const sent = claudeCode(on)
    await start($)
    const shown = await showModes($, hint)

    expect(sent.writes).toEqual(tty(shape))
    // The mod only reads the line: what Claude Code draws in it still shows.
    expect(shown).toEqual([hintLine(hint)])
  })
}

test('the cursor shape is written only when it changes', async ($, on) => {
  const sent = claudeCode(on)
  await start($)
  await showModes($, INSERT, INSERT, NORMAL, VISUAL, NORMAL, INSERT, INSERT)

  expect(sent.writes).toEqual(tty(BAR, BLOCK, BAR))
})

for (const reason of ['prompt_input_exit', 'logout', 'other'] as const) {
  test(`leaving the session (${reason}) gives the terminal its own cursor back`, async ($, on) => {
    const sent = claudeCode(on)
    await start($)
    await showModes($, INSERT, NORMAL)
    await end($, reason)

    expect(sent.writes).toEqual(tty(BAR, BLOCK, DEFAULT))
  })
}

// After /clear or a resume the process goes on under another session id, so the prompt
// stays on screen in its mode (SessionEndInput in the generated types).
for (const reason of ['clear', 'resume'] as const) {
  test(`${reason} keeps the cursor shape for the prompt still on screen`, async ($, on) => {
    const sent = claudeCode(on)
    await start($)
    await showModes($, NORMAL)
    await end($, reason)

    expect(sent.writes).toEqual(tty(BLOCK))
  })
}

test('an exit after a /clear still gives the terminal its own cursor back', async ($, on) => {
  const sent = claudeCode(on)
  await start($)
  await showModes($, NORMAL)
  await end($, 'clear')
  await end($, 'prompt_input_exit')

  expect(sent.writes).toEqual(tty(BLOCK, DEFAULT))
})

// The mode shows only in vim mode, and only while the hint line carries its label.
test('only a prompt whose vim mode shows gets its cursor shaped, and only it is reset at exit', async ($, on) => {
  const settings = { current: {} as Settings }
  const sent = claudeCode(on, settings)
  async function session(editor: Settings) {
    settings.current = editor
    const from = sent.writes.length
    await start($)
    await showModes($, NORMAL, INSERT)
    await end($, 'prompt_input_exit')
    return sent.writes.slice(from)
  }

  expect(await session({})).toEqual([])
  expect(await session({ editorMode: 'normal' })).toEqual([])
  expect(await session(HIDDEN_LABEL)).toEqual([])
  // The same session in vim mode, so the test can't pass on a mod that does nothing.
  expect(await session(VIM)).toEqual(tty(BLOCK, BAR, DEFAULT))
  expect(await session(labelHidden(false))).toEqual(tty(BLOCK, BAR, DEFAULT))
})

// /config changes the settings while the session runs; the mod has to follow at the next draw.
for (const [what, off] of [
  ['vim mode is turned off', { editorMode: 'normal' }],
  ['the vim mode label is hidden', HIDDEN_LABEL],
] as const) {
  test(`when ${what} mid-session the terminal gets its own cursor back, until the mode shows again`, async ($, on) => {
    const settings = { current: VIM }
    const sent = claudeCode(on, settings)
    await start($)
    const ui = await mountHint($, INSERT)
    settings.current = off
    await ui.redraw(hintProps(NORMAL))
    await ui.redraw(hintProps(INSERT))
    settings.current = VIM
    await ui.redraw(hintProps(NORMAL))
    settings.current = off
    await ui.redraw(hintProps(INSERT))
    await end($, 'prompt_input_exit')

    expect(sent.writes).toEqual(tty(BAR, DEFAULT, BLOCK, DEFAULT))
  })
}

test('ctrl+c clears the prompt, mid-turn too, and never stops a running turn', async ($, on) => {
  const sent = claudeCode(on)
  await start($)
  await $.turn.start({ text: 'write a long poem', turnId: 't1' })
  await clearCommand($)

  // `immediate` runs a command typed while a turn is in flight at once (CommandSpec.immediate).
  expect(sent.registered).toEqual([expect.objectContaining({ name: 'vim-ux-clear', immediate: true })])
  expect(sent.fills).toEqual([{ text: '', mode: 'replace' }])
  expect(sent.aborted).toEqual([])
})

// Ctrl+C is the user's only change to commands: Claude Code's own still run and show as before.
test('only the clear command stays out of the typeahead and leaves nothing in the transcript', async ($, on) => {
  const sent = claudeCode(on)
  await start($)
  const show = async (command: string) => {
    const described = await $.command.describe({
      command,
      description: 'A command',
      isHidden: false,
      immediate: false,
      provider: { plugin: 'engine', tier: 'core' },
    })
    return described.isHidden
  }
  const run = (command: string) =>
    $.command.run({
      command,
      args: '',
      origin: { kind: 'composer' },
      presentation: { isFullscreen: false, columns: 80 },
    })

  expect(await show('vim-ux-clear')).toBe(true)
  // No text means no transcript row; no context means no note for the model (CommandRunResult).
  expect(await run('vim-ux-clear')).toEqual({})
  expect(sent.fills).toHaveLength(1)

  expect(await show('help')).toBe(false)
  expect(await run('help')).toEqual({ text: 'Claude Code ran it' })
  expect(sent.fills).toHaveLength(1)
})

test('a fresh load draws the prompt hint again, so the cursor matches the mode at once', async ($, on) => {
  const sent = claudeCode(on)
  await start($)

  expect(sent.invalidated).toContainEqual({ event: 'ui.render' })
})
