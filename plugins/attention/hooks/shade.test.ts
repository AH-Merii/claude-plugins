import { expect, test } from 'claude-code/testing'

import { shade } from './shade'

test('a named colour is shaded from what Claude Code draws for it, not from xterm', () => {
  // Claude Code draws green #44a857, cyan #01a3c3 and blue #3c63de; xterm's are #00cd00, #00cdcd and #0000ee.
  expect(shade('green')).toBe('#41a053')
  expect(shade('cyan')).toBe('#019bb9')
  expect(shade('blue')).toBe('#395ed3')
})

test('a hex colour is shaded as given', () => {
  expect(shade('#ff8700')).toBe('#f28000')
  expect(shade('#FF8700')).toBe('#f28000')
})

test('a theme key or an unknown colour has no shade, so the caller can fall back', () => {
  for (const color of ['inactive', 'warning', 'teal', '#fff']) {
    expect(shade(color)).toBeUndefined()
  }
})
