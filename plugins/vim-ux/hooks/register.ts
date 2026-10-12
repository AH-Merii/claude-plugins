import type { Register } from 'claude-code'

// DECSCUSR, steady shapes: a bar in INSERT, a block in NORMAL and VISUAL, and 0 for the terminal's own.
const BAR = '\x1b[6 q'
const BLOCK = '\x1b[2 q'
const DEFAULT = '\x1b[0 q'
const TTY = '/dev/tty'

const CLEAR = 'vim-ux-clear'

export const register: Register = on => {
  // The shape last written, '' for the terminal's own: shapes are written only when they change.
  let shape = ''

  on('session.start', async ($, e, next) => {
    // Bound to Ctrl+C in keybindings.json; `immediate` runs it at once while a turn is in flight.
    await $.command.register({ name: CLEAR, description: 'Clears the prompt', immediate: true })
    // Draw the prompt hint again, so a fresh load reads the mode without waiting for a key.
    $.ui.invalidate('ui.render')
    return next(e)
  })

  on('command.describe', { command: CLEAR }, (_$, e, next) => next({ ...e, isHidden: true }))

  // Answering with no text leaves no transcript row, and the turn runs on: only Esc stops it.
  on('command.run', { command: CLEAR }, async $ => {
    await $.prompt.fill({ text: '', mode: 'replace' })
    return {}
  })

  // The hint line is the only place the vim mode shows: it holds `-- INSERT --` or `-- VISUAL --`
  // among its other parts, and no label in NORMAL. With statusLine.hideVimModeIndicator the label
  // moves to the status line, out of a mod's reach. Settings are read on every draw, since /config
  // can change them mid-session; when the mode can't be read, the terminal gets its own cursor back.
  on('ui.render', { component: 'PromptHint', surface: 'terminal' }, async ($, e, next) => {
    const { editorMode, statusLine } = await $.settings.read()
    const isLabelHidden = (statusLine as { hideVimModeIndicator?: unknown } | undefined)?.hideVimModeIndicator === true
    const want = editorMode !== 'vim' || isLabelHidden ? '' : e.props.hint.includes('-- INSERT --') ? BAR : BLOCK
    if (want !== shape) {
      shape = want
      await $.fs.write(TTY, want || DEFAULT)
    }
    return next(e)
  })

  // After /clear or a resume the prompt stays on screen, so its shape stays too.
  on('session.end', async ($, e, next) => {
    if (shape && e.reason !== 'clear' && e.reason !== 'resume') await $.fs.write(TTY, DEFAULT)
    return next(e)
  })
}
