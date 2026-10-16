import { expect, test } from 'claude-code/testing'

import { configure } from './categories'

const DEFAULT_IDS = ['must-know', 'decide-now', 'decide-later', 'suggest', 'default', 'your-action', 'optional']

test('with no config the default categories apply, decisions pinned', () => {
  const { categories, errors } = configure(undefined)

  expect(categories.map(c => c.id)).toEqual(DEFAULT_IDS)
  expect(categories.filter(c => c.pin).map(c => c.id)).toEqual(['decide-now', 'decide-later'])
  expect(errors).toEqual([])
})

test('a default is changed only in the fields given, and can be turned off', () => {
  const { categories, errors } = configure({
    categories: { 'decide-now': { color: '#ff0000' }, optional: { enabled: false } },
  })
  const defaults = configure(undefined).categories

  expect(categories.map(c => c.id)).toEqual(DEFAULT_IDS.filter(id => id !== 'optional'))
  expect(categories.find(c => c.id === 'decide-now')).toEqual({
    ...defaults.find(c => c.id === 'decide-now'),
    color: '#ff0000',
  })
  expect(errors).toEqual([])
})

test('a new category is added after the defaults, unpinned and undimmed but tinted, unless it says otherwise', () => {
  const { categories } = configure({
    categories: { 'ci-red': { label: 'CI RED', color: 'red', meaning: 'a check that failed' } },
  })

  expect(categories.at(-1)).toEqual({
    id: 'ci-red',
    label: 'CI RED',
    color: 'red',
    meaning: 'a check that failed',
    pin: false,
    dim: false,
    tint: true,
  })
})

test('an entry that cannot be used is named and left out, and the rest still apply', () => {
  for (const [id, entry, error] of [
    ['ci-red', { label: 'CI RED', color: 'red' }, /needs "meaning"/],
    ['decide-now', { pin: 'yes' }, /"pin" must be true or false/],
    ['your-action', { tint: 1 }, /"tint" must be true or false/],
    ['decide-now', { colour: 'red' }, /unknown field "colour"/],
    ['decide-now', { label: '' }, /"label" must be a non-empty string/],
    ['Decide Now', { color: 'red' }, /lowercase/],
    ['resolved', { label: 'DONE', color: 'green', meaning: 'done' }, /taken/],
    ['optional', 'off', /expected an object/],
  ] as const) {
    const { categories, errors } = configure({ categories: { [id]: entry, 'must-know': { color: 'blue' } } })

    expect(errors).toEqual([expect.stringMatching(error)])
    expect(categories.map(c => c.id)).toEqual(DEFAULT_IDS)
    expect(categories.find(c => c.id === 'must-know')?.color).toBe('blue')
  }
})

test('a config that is not an object of categories falls back to the defaults, saying so', () => {
  for (const raw of [[], 'red', null, { categories: [] }]) {
    const { categories, errors } = configure(raw)

    expect(categories.map(c => c.id)).toEqual(DEFAULT_IDS)
    expect(errors).toHaveLength(1)
  }
})
