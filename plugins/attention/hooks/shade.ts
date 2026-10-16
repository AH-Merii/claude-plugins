// The colour names Ink takes, as Claude Code draws them: its own RGB values, whatever the terminal's palette.
// Measured from the pixels of each name drawn in Claude Code 2.1.299 under its dark theme, in Ghostty.
const NAMED: Record<string, string> = {
  black: '#000000',
  red: '#e6464c',
  green: '#44a857',
  yellow: '#f5da03',
  blue: '#3c63de',
  magenta: '#d73ea0',
  cyan: '#01a3c3',
  white: '#ffffff',
  gray: '#8c8e99',
  grey: '#8c8e99',
  blackBright: '#8c8e99',
  redBright: '#ff6369',
  greenBright: '#5bd180',
  yellowBright: '#ffe724',
  blueBright: '#5b8eef',
  magentaBright: '#ef6ac3',
  cyanBright: '#3cc3e1',
  whiteBright: '#ffffff',
}

// How much of the colour a shade keeps.
const KEEP = 0.95

// A dimmer shade of a colour, as hex: a hex colour as given, a named one as Claude Code draws it. Undefined for a
// theme key, whose value the mod can't read. Claude Code's dimColor draws dim text grey whatever its colour, so
// the shade is worked out here.
export function shade(color: string): string | undefined {
  const hex = /^#[0-9a-f]{6}$/i.test(color) ? color : NAMED[color]
  if (hex === undefined) {
    return undefined
  }
  const channels = [1, 3, 5].map(i => Math.round(Number.parseInt(hex.slice(i, i + 2), 16) * KEEP))
  return `#${channels.map(c => c.toString(16).padStart(2, '0')).join('')}`
}
