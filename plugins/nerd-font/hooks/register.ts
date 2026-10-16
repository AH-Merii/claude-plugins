import type { EngineInterface as Engine, Register } from 'claude-code'

const enabled = { plugin: 'nerd-font', key: 'enabled' } as const

// Whether fontconfig lists a font family with "Nerd Font" in its name. The mod API can't tell which font the
// terminal draws with, so an installed one is the best guess; the setting covers a terminal that doesn't use it.
async function installed($: Engine) {
  try {
    const { stdout } = await $.process.run(['fc-list', ':', 'family'], { timeoutMs: 5000 })
    return stdout.includes('Nerd Font')
  } catch {
    // No fc-list on this machine, or no processes on this surface: glyphs would show as empty boxes.
    return false
  }
}

export const register: Register = (on, options) => {
  // The answer as last worked out; fonts don't change within a process, so it is checked once per load.
  let answer: boolean | undefined

  // Once a session, and again when the module reloads, as it does when the setting changes in /config.
  on('session.start', async ($, e, next) => {
    answer = options.glyphs === 'on' || (options.glyphs !== 'off' && (await installed($)))
    await $.state.set(enabled, answer)
    return next(e)
  })

  // A /clear starts a new session whose state starts empty, and no session.start fires for it; the settings-style
  // SessionStart does, with source "clear", inside the new session.
  on('classic.SessionStart', async ($, e, next) => {
    const result = await next(e)
    if (e.source === 'clear' && answer !== undefined) {
      await $.state.set(enabled, answer)
    }
    return result
  })
}
