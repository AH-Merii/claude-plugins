import type { On } from 'claude-code'
import { type Engine, expect, type MockClock, mock, test } from 'claude-code/testing'

const REPLY = 'Run this:\n\n```sh\nls -la\n```\n\nand this:\n\n```py\nprint(1)\n```'

test('each code block gets a copy row that copies its code', async ($, on) => {
  mock.clock(on)
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
  const drawn = {
    name: await ui.find({ type: 'Text', text: /averyvery/ }),
    buttons: await ui.findAll({ type: 'Button' }),
  }
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

test('the block opening a reply draws the bullet, and a later block does not', async $ => {
  for (const isFirstOfReply of [true, false]) {
    const ui = await $.ui.mount({
      plugin: 'copy-code',
      surface: 'terminal',
      component: 'AssistantMessage',
      props: { text: REPLY, isFirstOfReply },
    })
    const bullets = await ui.findAll({ type: 'Text', text: '●' })
    await ui.unmount()
    expect(bullets).toHaveLength(isFirstOfReply ? 1 : 0)
  }
})

const RAN = { stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }

// Answers the clipboard paths with the environment and wl-copy given, and logs what reached each, in order.
// On Wayland Claude Code's copy returns before its own wl-copy has written, which lands up to 30 ms later.
function clipboard(on: On, env: Record<string, string>, wlCopy: () => number) {
  const clock = mock.clock(on)
  mock.env(on, env)
  const seen = { clock, log: [] as string[], commands: [] as string[], toasts: [] as string[] }
  on('process.run', (_$, e) => {
    seen.log.push(`run: ${e.init?.stdin}`)
    seen.commands.push(e.argv.join(' '))
    return { value: { ...RAN, exitCode: wlCopy() } }
  })
  on('ui.copy', (_$, e) => {
    seen.log.push(`Claude Code: ${e.text}`)
    if (env.WAYLAND_DISPLAY) {
      void clock.sleep(30).then(() => seen.log.push(`wl-copy by Claude Code: ${e.text}`))
    }
    return { value: { isCopied: true } }
  })
  on('ui.toast', (_$, e) => {
    seen.toasts.push(e.text)
    return { value: undefined }
  })
  return seen
}

// Presses copy on the reply's `sh` block, and gives the copy up to 2 s.
async function copyShell($: Engine, clock: MockClock) {
  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: REPLY, isFirstOfReply: true },
  })
  const pressed = ui.press({ key: 'm1:copy:1' })
  await clock.advance(2000)
  await pressed
  await ui.unmount()
}

test('on Wayland Claude Code copies the code, then wl-copy puts it on the clipboard as plain text', async ($, on) => {
  const seen = clipboard(on, { WAYLAND_DISPLAY: 'wayland-1' }, () => 0)
  await copyShell($, seen.clock)

  expect(seen.log).toEqual(['Claude Code: ls -la', 'wl-copy by Claude Code: ls -la', 'run: ls -la'])
  expect(seen.commands[0]).toMatch(/\bwl-copy\b.*--type ["']?text\/plain;charset=utf-8\b/)
  expect(seen.toasts).toEqual(['Copied'])
})

test('without a Wayland display only Claude Code copies', async ($, on) => {
  const seen = clipboard(on, {}, () => 0)
  await copyShell($, seen.clock)

  expect(seen.log).toEqual(['Claude Code: ls -la'])
  expect(seen.toasts).toEqual(['Copied'])
})

test('over SSH only Claude Code copies, since wl-copy would reach the remote desktop', async ($, on) => {
  const seen = clipboard(
    on,
    { WAYLAND_DISPLAY: 'wayland-1', SSH_CONNECTION: '192.168.1.20 52144 192.168.1.10 22' },
    () => 0,
  )
  await copyShell($, seen.clock)

  expect(seen.log[0]).toBe('Claude Code: ls -la')
  expect(seen.commands).toEqual([])
  expect(seen.toasts).toEqual(['Copied'])
})

const FAILING_WL_COPY: [string, () => number][] = [
  ['fails', () => 1],
  [
    'cannot run',
    () => {
      throw new Error('wl-copy: not found')
    },
  ],
]

for (const [how, wlCopy] of FAILING_WL_COPY) {
  test(`when wl-copy ${how}, the copy by Claude Code still counts`, async ($, on) => {
    const seen = clipboard(on, { WAYLAND_DISPLAY: 'wayland-1' }, wlCopy)
    await copyShell($, seen.clock)

    expect(seen.log.filter(l => l.startsWith('Claude Code'))).toEqual(['Claude Code: ls -la'])
    expect(seen.toasts).toEqual(['Copied'])
  })
}

test('on Wayland "Copied" shows once Claude Code has copied, without waiting for wl-copy', async ($, on) => {
  const seen = clipboard(on, { WAYLAND_DISPLAY: 'wayland-1' }, () => 0)
  const ui = await $.ui.mount({
    plugin: 'copy-code',
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'm1',
    props: { text: REPLY, isFirstOfReply: true },
  })
  const pressed = ui.press({ key: 'm1:copy:1' })
  await seen.clock.settle()
  expect(seen.toasts).toEqual(['Copied'])

  await seen.clock.advance(2000)
  await pressed
  await ui.unmount()
  expect(seen.toasts).toEqual(['Copied'])
})
