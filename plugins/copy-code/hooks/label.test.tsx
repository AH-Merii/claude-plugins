import type { On } from 'claude-code'
import { type Engine, expect, type Plugin, test } from 'claude-code/testing'

// nf-fa-copy, U+F0C5, from a Nerd Font.
const NERD_FONT_LABEL = ' \uF0C5 copy '
const PLAIN_LABEL = ' copy '

// Stand-ins for the nerd-font mod, each giving its answer once the session starts.
const hasNerdFont: Plugin = {
  name: 'nerd-font',
  register(on) {
    on('session.start', async ($, e, next) => {
      await $.state.set({ plugin: 'nerd-font', key: 'enabled' }, true)
      return next(e)
    })
  },
}

const noNerdFont: Plugin = {
  name: 'nerd-font',
  register(on) {
    on('session.start', async ($, e, next) => {
      await $.state.set({ plugin: 'nerd-font', key: 'enabled' }, false)
      return next(e)
    })
  },
}

// Stands in for Claude Code's own drawing of the prose it is handed.
function engineDraws(on: On) {
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{e.props.text}</Text>
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
}

function start($: Engine) {
  return $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true } as never)
}

// A reply with a long language name, drawn 40 columns wide.
function mount($: Engine) {
  return $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    viewport: { columns: 40, rows: 40 },
    props: { text: 'A component:\n\n```typescriptreact\nexport const App = () => <main />\n```', isFirstOfReply: true },
  })
}

// The copy labels drawn, and whether the language name is drawn beside them.
async function topRow(ui: Awaited<ReturnType<typeof mount>>) {
  const labels = (await ui.findAll({ type: 'Button' })).map(b => b.props.label)
  const name = await ui.find({ type: 'Text', text: /typescriptreact/ })
  return { labels, isNamed: name !== undefined }
}

const cases = [
  { answer: 'there is a Nerd Font', nerdFont: hasNerdFont, shows: 'with the Nerd Font icon', label: NERD_FONT_LABEL },
  { answer: 'there is no Nerd Font', nerdFont: noNerdFont, shows: 'in plain text', label: PLAIN_LABEL },
] as const

for (const c of cases) {
  test(
    `when nerd-font says ${c.answer}, copy is labelled ${c.shows} beside the language name`,
    { plugins: [c.nerdFont] },
    async ($, on) => {
      engineDraws(on)
      await start($)

      const ui = await mount($)
      const row = await topRow(ui)
      await ui.unmount()

      expect(row).toEqual({ labels: [c.label], isNamed: true })
    },
  )
}

test(
  'before nerd-font has answered copy is labelled in plain text, and gains the icon once it says yes',
  { plugins: [hasNerdFont] },
  async ($, on) => {
    engineDraws(on)
    // nerd-font answers once the session starts; a reply drawn before then reads undefined.
    const ui = await mount($)
    const before = await topRow(ui)

    await start($)
    const after = await topRow(ui)
    await ui.unmount()

    expect(before).toEqual({ labels: [PLAIN_LABEL], isNamed: true })
    expect(after).toEqual({ labels: [NERD_FONT_LABEL], isNamed: true })
  },
)
