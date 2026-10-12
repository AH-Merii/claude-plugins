import { expect, test } from 'claude-code/testing'

import { split } from './split'

test('splits prose and fenced code, keeping the code body and language', () => {
  const segments = split('Run this:\n\n```sh\nls -la\necho hi\n```\n\nThen done.')
  expect(segments.map(s => s.kind)).toEqual(['prose', 'code', 'prose'])
  expect(segments[1]).toEqual({
    kind: 'code',
    text: '```sh\nls -la\necho hi\n```',
    code: 'ls -la\necho hi',
    language: 'sh',
  })
})

test('a fence without a language has none', () => {
  expect(split('```\nx\n```')[0]).toEqual({ kind: 'code', text: '```\nx\n```', code: 'x' })
})

test('a longer fence holds a shorter one inside it', () => {
  const segments = split('````md\n```js\nx\n```\n````')
  expect(segments).toHaveLength(1)
  expect(segments[0]).toMatchObject({ kind: 'code', code: '```js\nx\n```', language: 'md' })
})

test('text without fences is one prose segment', () => {
  expect(split('just words').map(s => s.kind)).toEqual(['prose'])
})

test('blank lines between back-to-back blocks are not a prose segment', () => {
  expect(split('```\na\n```\n\n```\nb\n```').map(s => s.kind)).toEqual(['code', 'code'])
})

test('a backtick line whose info string holds a backtick is prose, not a fence', () => {
  for (const line of ['```npm i``` installs it.', '```js `x`']) {
    const segments = split(`${line}\n\nThen run:\n\n\`\`\`sh\nls\n\`\`\``)
    expect(segments.map(s => s.kind)).toEqual(['prose', 'code'])
    expect(segments[1]).toMatchObject({ code: 'ls', language: 'sh' })
  }
})

test('a tilde fence may hold a backtick in its info string', () => {
  expect(split('~~~js `x`\ny\n~~~')).toEqual([{ kind: 'code', text: '~~~js `x`\ny\n~~~', code: 'y', language: 'js' }])
})

test('an indented fence drops up to its own indent from each code line', () => {
  const segments = split('1. Item:\n\n   ```sh\n   echo in-list\n     nested\n  less\n   ```\n2. Next.')
  expect(segments.map(s => s.kind)).toEqual(['prose', 'code', 'prose'])
  expect(segments[1]).toMatchObject({ code: 'echo in-list\n  nested\nless', indent: 3 })
})
