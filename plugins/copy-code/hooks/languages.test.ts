import { expect, test } from 'claude-code/testing'

import { languageName, NAMES } from './languages'

test('every alias is looked up whatever its case', () => {
  for (const alias of Object.keys(NAMES)) {
    expect(languageName(alias.toUpperCase())).toBe(languageName(alias))
  }
})

test('a language that is not an alias is shown as written', () => {
  expect(languageName('Not-A-Language')).toBe('Not-A-Language')
})

test('a language named after an object property is shown as written', () => {
  const names = [...Object.getOwnPropertyNames(Object.prototype), 'CONSTRUCTOR']
  expect(names).toContain('__proto__')
  for (const name of names) {
    expect(languageName(name)).toBe(name)
  }
})
