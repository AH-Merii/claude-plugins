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
