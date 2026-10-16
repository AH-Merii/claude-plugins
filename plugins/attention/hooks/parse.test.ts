import { expect, test } from 'claude-code/testing'

import { parse } from './parse'

const TAGS = new Set(['must-know', 'decide-now', 'decide-later', 'optional'])

test('tagged lines come out of the reply wherever they sit, in order, with their ids', () => {
  const reply = [
    'Merged #72; CI is green.',
    '',
    '> [!must-know] The Outlook wizard never ran against a real account.',
    '',
    'Next I start on slice 16.',
    '',
    '> [!decide-now] D4: File both issues as drafted?',
    '> [!decide-later] D5 — Go past slice 15? (after D4)',
  ].join('\n')

  const { items, rest } = parse(reply, TAGS)

  expect(items).toEqual([
    { tag: 'must-know', text: 'The Outlook wizard never ran against a real account.' },
    { tag: 'decide-now', id: 'D4', text: 'File both issues as drafted?' },
    { tag: 'decide-later', id: 'D5', text: 'Go past slice 15? (after D4)' },
  ])
  expect(rest).toBe('Merged #72; CI is green.\n\n\nNext I start on slice 16.')
})

test('a quoted line that follows an item carries it on', () => {
  const reply = '> [!decide-now] D1: Merge #41 as is,\n> or push the cleanup first?\n\nDone.'

  const { items, rest } = parse(reply, TAGS)

  expect(items).toEqual([{ tag: 'decide-now', id: 'D1', text: 'Merge #41 as is, or push the cleanup first?' }])
  expect(rest).toBe('\nDone.')
})

test('a tag that is not a category stays in the reply, as do other quotes', () => {
  const reply = '> [!NOTE] GitHub draws this one.\n> [!blocked] Not a category here.\n> A plain quote.'

  expect(parse(reply, TAGS)).toEqual({ items: [], rest: reply })
})

test('settled lines are read whatever the categories are', () => {
  expect(parse('> [!resolved] D4: filing both', new Set()).items).toEqual([
    { tag: 'resolved', id: 'D4', text: 'filing both' },
  ])
})

test('tags quoted inside a code block are shown, not taken', () => {
  for (const fence of ['```', '~~~', '````']) {
    const reply = `Write it like this:\n\n${fence}md\n> [!decide-now] D1: Merge?\n${fence}\n\n> [!optional] Want a template?`

    const { items, rest } = parse(reply, TAGS)

    expect(items).toEqual([{ tag: 'optional', text: 'Want a template?' }])
    expect(rest).toBe(`Write it like this:\n\n${fence}md\n> [!decide-now] D1: Merge?\n${fence}`)
  }
})
