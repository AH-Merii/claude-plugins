import { expect, test } from 'claude-code/testing'

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
