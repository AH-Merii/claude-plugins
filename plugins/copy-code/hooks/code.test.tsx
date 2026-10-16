import { type Engine, expect, mock, test } from 'claude-code/testing'

function mount($: Engine, text: string) {
  return $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text, isFirstOfReply: true },
  })
}

// The fenced blocks drawn for the code, each as [fence, info, body, closing fence].
async function fencesOf(ui: Awaited<ReturnType<typeof mount>>) {
  const markdown = await ui.findAll({ type: 'Markdown', text: /^`{3,}/ })
  return markdown.map(m => /^(`+)([^\n]*)\n([\s\S]*)\n(`+)$/.exec(String(m.props.text)))
}

test('code holding a markdown fence is drawn only as one fenced block it cannot close, and copies as written', async ($, on) => {
  // Stands in for Claude Code's own drawing of the prose it is handed.
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{e.props.text}</Text>
  })
  mock.clock(on)
  mock.env(on, {})
  const copied: string[] = []
  on('ui.copy', (_$, e) => {
    copied.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', () => ({ value: undefined }))

  const code = '## Install\n\n```sh\nnpm install copy-code\n```\n\nThen restart Claude Code.'
  const ui = await mount($, `Add this to the README:\n\n\`\`\`\`md\n${code}\n\`\`\`\`\n`)
  // The leaves drawing the code; a Box's text holds its children's.
  const drawings = (await ui.findAll({ text: 'npm install copy-code' })).filter(d => d.type !== 'Box')
  const fences = await fencesOf(ui)
  await ui.press({ key: 'm1:copy:1' })
  await ui.unmount()

  expect(drawings.length).toBeGreaterThan(0)
  expect(drawings.map(d => d.type)).toEqual(drawings.map(() => 'Markdown'))
  expect(fences).toHaveLength(drawings.length)
  for (const fence of fences) {
    expect(fence?.[3]).toBe(code)
    expect(fence?.[4]).toBe(fence?.[1])
    const closer = new RegExp(`^ {0,3}\`{${fence?.[1]?.length},}\\s*$`)
    expect(code.split('\n').filter(line => closer.test(line))).toEqual([])
  }
  expect(copied).toEqual([code])
})

test('a fence names the language Claude Code highlights it by, plain text when it has none, and nothing without one', async $ => {
  for (const [language, info] of [
    ['not-a-language', 'plaintext'],
    ['python', 'python'],
    ['PY', 'py'],
    ['typescript:src/app.ts', 'typescript'],
    ['', ''],
  ]) {
    const ui = await mount($, `\`\`\`${language}\nx\n\`\`\``)
    const fences = await fencesOf(ui)
    await ui.unmount()

    expect(fences.length).toBeGreaterThan(0)
    for (const fence of fences) {
      expect(fence?.[2]?.toLowerCase()).toBe(info)
    }
  }
})

test("the prose around code is handed to the plugins beneath, and only the reply's first block opens it", async ($, on) => {
  // Stands in for a plugin beneath, such as one drawing tagged lines of the reply in colour.
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{`beneath${e.props.isFirstOfReply ? ' (opens the reply)' : ''}: ${e.props.text.trim()}`}</Text>
  })

  const ui = await mount(
    $,
    'Run this:\n\n```sh\nls -la\n```\n\nIt lists hidden files too.\n\n> [!optional] O1: Want me to add a `--sort` flag?',
  )
  const beneath = await ui.findAll({ type: 'Text', text: /^beneath/ })
  const buttons = await ui.findAll({ type: 'Button' })
  await ui.unmount()

  expect(beneath.map(b => b.text)).toEqual([
    'beneath (opens the reply): Run this:',
    'beneath: It lists hidden files too.\n\n> [!optional] O1: Want me to add a `--sort` flag?',
  ])
  expect(buttons.map(b => b.key)).toEqual(['m1:copy:1'])
})

test('a reply with code too long for Claude Code to draw as markdown is left to Claude Code', async ($, on) => {
  // Stands in for Claude Code's own drawing of the reply.
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>native</Text>
  })
  const lines = Array.from({ length: 300 }, (_, i) => `    rows.append(load_row(path, index=${i}, strict=True))`)

  const ui = await mount(
    $,
    `Here is the loader:\n\n\`\`\`python\ndef load(path):\n    rows = []\n${lines.join('\n')}\n\`\`\``,
  )
  const drawn = await ui.drawn()
  await ui.unmount()

  expect(drawn).toMatchObject({ type: 'Text', children: ['native'] })
})
