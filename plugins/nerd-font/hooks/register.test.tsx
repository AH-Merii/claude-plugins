import type { On } from 'claude-code'
import { type Engine, expect, type Plugin, test } from 'claude-code/testing'

const NERD = ['FiraCode Nerd Font,FiraCode Nerd Font Light', 'DejaVu Sans Mono', 'Noto Color Emoji']
const PLAIN = ['DejaVu Sans Mono', 'Noto Color Emoji', 'Liberation Serif']

// Stands in for fontconfig: `fc-list : family` lists the installed families, one per line; `missing` is a machine
// without fc-list, where the call can't start.
function fonts(on: On, families: readonly string[] | 'missing') {
  on('process.run', (_$, e) => {
    if (families === 'missing' || e.argv.join(' ') !== 'fc-list : family') {
      return { deny: `${e.argv[0]}: command not found` }
    }
    const stdout = families.map(f => `${f}\n`).join('')
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
}

function start($: Engine, on: On) {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  return $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true } as never)
}

// A mod that depends on nerd-font and draws the answer it reads, so a value never written shows as `undefined`.
const reader: Plugin = {
  name: 'reader',
  register(on) {
    on('ui.render', { component: 'AbovePrompt' }, async ($, e) => {
      const { value } = await $.state.get({ plugin: 'nerd-font', key: 'enabled' })
      const { Text } = $.ui.resolve(e)
      return <Text>{String(value)}</Text>
    })
  },
}

// A mod that depends on nerd-font, drawing attention's magnifying glass or its fallback.
const magnifier: Plugin = {
  name: 'magnifier',
  register(on) {
    on('ui.render', { component: 'AbovePrompt' }, async ($, e) => {
      const { value } = await $.state.get({ plugin: 'nerd-font', key: 'enabled' })
      const { Text } = $.ui.resolve(e)
      return <Text>{value ? '\u{F0349}' : '🔍'}</Text>
    })
  },
}

// What a dependent mod draws in the band.
async function drawn($: Engine, plugin: string) {
  const ui = await $.ui.mount({
    plugin,
    surface: 'terminal',
    component: 'AbovePrompt',
    requestId: 'band',
    props: { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 100 } as never,
  })
  const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text)
  await ui.unmount()
  return texts
}

const cases = [
  { name: 'auto, with a Nerd Font installed', glyphs: 'auto', families: NERD, expected: 'true' },
  { name: 'auto, with no Nerd Font installed', glyphs: 'auto', families: PLAIN, expected: 'false' },
  { name: 'auto, on a machine without fc-list', glyphs: 'auto', families: 'missing', expected: 'false' },
  { name: 'on, with no Nerd Font installed', glyphs: 'on', families: PLAIN, expected: 'true' },
  { name: 'off, with a Nerd Font installed', glyphs: 'off', families: NERD, expected: 'false' },
] as const

for (const c of cases) {
  test(
    `glyphs are ${c.expected === 'true' ? 'on' : 'off'} when the setting is ${c.name}`,
    { options: { glyphs: c.glyphs }, plugins: [reader] },
    async ($, on) => {
      fonts(on, c.families)
      await start($, on)

      expect(await drawn($, 'reader')).toEqual([c.expected])
    },
  )
}

test(
  'a mod that depends on nerd-font picks its glyph from the answer while drawing',
  { plugins: [magnifier] },
  async ($, on) => {
    fonts(on, NERD)
    await start($, on)

    expect(await drawn($, 'magnifier')).toEqual(['\u{F0349}'])
  },
)
