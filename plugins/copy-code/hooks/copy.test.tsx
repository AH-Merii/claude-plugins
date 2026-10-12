import { type Engine, expect, mock, test } from 'claude-code/testing'

const REPLY = 'Run this:\n\n```sh\nls -la\n```\n\nand this:\n\n```py\nprint(1)\n```'

test('each code block gets a copy row that copies its code', async ($, on) => {
  const copied: string[] = []
  on('ui.copy', (_$, e) => {
    copied.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', () => ({ value: undefined }))

  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: REPLY, isFirstOfReply: true },
  })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.press({ key: 'm1:copy:3' })
  await ui.press({ key: 'm1:copy:1' })
  await ui.unmount()

  expect(copied).toEqual(['print(1)', 'ls -la'])
})

test('an empty block draws no copy button', async ($, on) => {
  on('ui.copy', () => ({ value: { isCopied: true } }))
  on('ui.toast', () => ({ value: undefined }))

  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: 'Empty:\n\n```\n```\n\nand:\n\n```py\n```\n\nfull:\n\n```sh\nls\n```', isFirstOfReply: true },
  })
  const buttons = await ui.findAll({ type: 'Button' })
  await ui.unmount()

  expect(buttons.map(b => b.key)).toEqual(['m1:copy:5'])
})

const LONG = 'averyveryverylonglanguagenamethatkeepsgoingandgoing'

async function drawAt($: Engine, columns: number) {
  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    viewport: { columns, rows: 40 },
    props: { text: `\`\`\`${LONG}\nx\n\`\`\``, isFirstOfReply: true },
  })
  const drawn = { name: await ui.find({ type: 'Text', text: /averyvery/ }), buttons: await ui.findAll({ type: 'Button' }) }
  await ui.unmount()
  return drawn
}

test('a language name is left out when it would get only a few cells, and copy stays', async $ => {
  const wide = await drawAt($, 60)
  expect(wide.name).toBeDefined()

  const narrow = await drawAt($, 16)
  expect(narrow.name).toBeUndefined()
  expect(narrow.buttons).toHaveLength(1)
})

test('a terminal too narrow for a box leaves the reply to Claude Code', async ($, on) => {
  // Stands in for Claude Code's own drawing of the reply.
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>native</Text>
  })

  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    viewport: { columns: 10, rows: 40 },
    props: { text: '```sh\nls\n```', isFirstOfReply: true },
  })
  const drawn = await ui.drawn()
  await ui.unmount()

  expect(drawn).toMatchObject({ type: 'Text', children: ['native'] })
})

test('quick presses all copy, and a toast repeats only once it has gone', async ($, on) => {
  const clock = mock.clock(on)
  const copied: string[] = []
  const toasts: { text: string; timeoutMs?: number }[] = []
  on('ui.copy', (_$, e) => {
    copied.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e)
    return { value: undefined }
  })

  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: REPLY, isFirstOfReply: true },
  })
  await ui.press({ key: 'm1:copy:1' })
  await clock.advance(1000)
  await ui.press({ key: 'm1:copy:3' })
  expect(copied).toEqual(['ls -la', 'print(1)'])
  expect(toasts.map(t => t.text)).toEqual(['Copied'])

  await clock.advance(toasts[0]?.timeoutMs ?? 4000)
  await ui.press({ key: 'm1:copy:3' })
  await ui.unmount()
  expect(toasts.map(t => t.text)).toEqual(['Copied', 'Copied'])
})

test('a failed copy is announced even while "Copied" shows', async ($, on) => {
  mock.clock(on)
  let isCopied = true
  const toasts: string[] = []
  on('ui.copy', () => ({ value: isCopied ? { isCopied: true } : { isCopied: false, reason: 'no-clipboard' } }))
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })

  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: REPLY, isFirstOfReply: true },
  })
  await ui.press({ key: 'm1:copy:1' })
  isCopied = false
  await ui.press({ key: 'm1:copy:3' })
  await ui.unmount()

  expect(toasts).toEqual(['Copied', 'Copy failed: no-clipboard'])
})
