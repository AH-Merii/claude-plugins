import type { On, RenderSurface } from 'claude-code'
import { type Engine, expect, test } from 'claude-code/testing'

// Stands in for the engine's own composition of the system prompt.
const ENGINE = [
  { id: 'intro', text: 'You are Claude Code.', scope: 'shared' },
  { id: 'tools', text: 'Use the tools offered.', scope: 'shared' },
  { id: 'env', text: 'Working directory: /work', scope: 'session' },
] as const

function engine(on: On) {
  on('prompt.compose', () => ({ sections: ENGINE }))
}

// A test session has no facts of its own to fill in, so each is given.
function compose($: Engine, surfaces: RenderSurface[]) {
  const model = 'claude-haiku'
  return $.prompt.compose({ model, promptModel: model, surfaces, tools: [], outputStyle: null, traits: [] })
}

test('the fence reminder is added only where the session draws in a terminal', async ($, on) => {
  engine(on)
  for (const [surfaces, isAdded] of [
    [['terminal'], true],
    [['terminal', 'desktop'], true],
    [[], false],
    [['desktop'], false],
  ] as const) {
    expect((await compose($, [...surfaces])).sections.map(s => s.id)).toEqual(
      isAdded ? ['intro', 'tools', 'env', 'copy-code:fences'] : ['intro', 'tools', 'env'],
    )
  }
})

test('the reminder follows the engine sections, unchanged, as a session section asking for a language tag', async ($, on) => {
  engine(on)
  const { sections } = await compose($, ['terminal'])

  expect(sections.slice(0, ENGINE.length)).toEqual(ENGINE)
  expect(sections.slice(ENGINE.length)).toEqual([
    { id: 'copy-code:fences', text: expect.stringMatching(/language tag/), scope: 'session' },
  ])
})
