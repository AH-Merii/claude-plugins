import type { Register } from 'claude-code'

import { fence } from './fence'
import { languageName } from './languages'
import { split } from './split'

const MAX = 10000

// nf-fa-copy, from a Nerd Font.
const ICON = '\uF0C5'
const LABEL = ` ${ICON} copy `
// The cells right of the language name: the corner, the copy label and a gap.
const RIGHT = 2 + LABEL.length + 1
// With fewer cells than this a name says nothing, so it is left out.
const MIN_NAME = 4
// The reply's left gutter, as Claude Code draws it on the block opening a reply, the bullet in it. A block that
// doesn't open one it draws with no gutter.
const GUTTER = 2
// Narrower than this a box can't hold its corners and copy, so Claude Code draws the reply.
const MIN_COLUMNS = 12
// How long a toast stays; Claude Code's default.
const TOAST_MS = 4000
// Copies stdin as plain text. Claude Code runs wl-copy without --type, so wl-copy guesses one: `x` lands as
// application/octet-stream and HTML as text/html, which a paste as text can't read. Its output goes to /dev/null,
// since the clipboard server it leaves running would hold the pipes open until the call timed out.
const WL_COPY = ['sh', '-c', "exec wl-copy --type 'text/plain;charset=utf-8' >/dev/null 2>&1"]
// How long wl-copy may take before Claude Code's copy is left to stand.
const WL_COPY_MS = 2000
// Claude Code's own wl-copy lands after its copy call returns: up to 28 ms after a typed copy run at once, in
// six live runs. The typed copy waits this long so it lands last.
const WL_COPY_AFTER_MS = 300
// Asks Claude to tag every fence: an untagged block gets no name and no colours. Claude leaves a fence untagged
// most often when its code isn't valid on its own. The text never varies, so the cached prompt before it holds.
const FENCES =
  'Code blocks in your replies are boxed by copy-code, which names and colours each by its fence language. ' +
  'Give every fenced block a language tag (python, bash, json; text for plain output). For a sketch that is ' +
  'not valid code on its own, tag the real language it is closest to: a made-up tag such as pseudo gets no colours.'

export const register: Register = on => {
  // Only where a terminal draws the replies: in print mode or the Desktop app the box isn't there.
  on('prompt.compose', async (_$, e, next) => {
    const composed = await next(e)
    if (!e.surfaces.includes('terminal')) {
      return composed
    }
    return { sections: [...composed.sections, { id: 'copy-code:fences', text: FENCES, scope: 'session' }] }
  })

  // The toast showing, if any. Raising another relays out the transcript, which can drop a press in flight.
  let toast = { text: '', until: 0 }

  on('ui.render', { component: 'AssistantMessage', surface: 'terminal' }, async ($, e, next) => {
    const segments = split(e.props.text).map(s => ({
      ...s,
      drawn: s.kind === 'code' ? fence(s.code, s.language) : s.text,
    }))
    const isDrawable = segments.some(s => s.kind === 'code') && segments.every(s => s.drawn.length <= MAX)

    const columns = e.viewport?.columns
    if (!isDrawable || (columns !== undefined && columns < MIN_COLUMNS)) {
      return next(e)
    }

    const { Box, Button, Markdown, Text } = $.ui.resolve(e)

    // After Claude Code's copy, on Wayland and not over SSH (where wl-copy would reach the remote desktop),
    // wl-copy puts the code back on the clipboard typed as text. When wl-copy fails or is missing, Claude Code's
    // copy stands.
    const retype = async (text: string) => {
      if ((await $.env.get('WAYLAND_DISPLAY')) && !(await $.env.get('SSH_CONNECTION'))) {
        await $.clock.sleep(WL_COPY_AFTER_MS)
        await $.process.run(WL_COPY, { stdin: text, timeoutMs: WL_COPY_MS }).catch(() => undefined)
      }
    }

    // The prose goes to the plugins beneath and then Claude Code, as a block of its own each, so a plugin that
    // draws from the reply's text still sees it. Only the first can open the reply: Claude Code draws it with the
    // gutter and bullet, the later ones with no gutter, so they get one here.
    const gutter = e.props.isFirstOfReply ? GUTTER : 0
    const prose = await Promise.all(
      segments.map((s, i) =>
        s.kind === 'prose'
          ? next({ ...e, props: { ...e.props, text: s.text, isFirstOfReply: e.props.isFirstOfReply && i === 0 } })
          : undefined,
      ),
    )

    return (
      <Box flexDirection="column">
        {segments.map((s, i) => {
          // Claude Code draws a blank row above each block, so a prose segment brings its own and a box adds one.
          if (s.kind === 'prose') {
            return (
              <Box key={`${e.requestId}:${i}`} marginLeft={i === 0 ? 0 : gutter}>
                {prose[i]}
              </Box>
            )
          }

          // Claude Code copies first: its own wl-copy, the primary selection, a tmux buffer and the terminal's
          // OSC 52. Its result is what the toast says, so the toast shows before the retype.
          const copy = async () => {
            const result = await $.ui.copy({ text: s.code, surface: 'terminal' })
            const text = result.isCopied ? 'Copied' : `Copy failed: ${result.reason}`
            const now = await $.clock.now()
            if (text !== toast.text || now >= toast.until) {
              toast = { text, until: now + TOAST_MS }
              $.ui.toast(text, { timeoutMs: TOAST_MS })
            }
            await retype(s.code)
          }

          // Not the wrapper's key: a keyed Box is a scope of its own, and hovering the code would join it.
          const scope = `${e.requestId}:${i}:lit`
          // The name's cells: the box less its left corner, the right side and a space either side.
          const room = columns === undefined ? Infinity : columns - gutter - (s.indent ?? 0) - 2 - RIGHT - 2
          const name = s.language !== undefined && room >= MIN_NAME ? languageName(s.language) : undefined

          // The overlay redraws the whole box lit, so hovering the code lights nothing. The top row (name and copy)
          // lies over the top border in the flow, so it scrolls away with the block: absolute, it was pinned to the
          // viewport's top row once the block scrolled off. Column-reverse lays it out first but draws it last,
          // over the overlay, so the name stays unlit: under the overlay it kept the lit background afterwards.
          return (
            <Box key={`${e.requestId}:${i}`} flexDirection="row" marginTop={1}>
              <Box width={gutter} flexShrink={0}>
                {e.props.isFirstOfReply && i === 0 && <Text color="text">●</Text>}
              </Box>
              <Box flexDirection="column-reverse" flexGrow={1} marginLeft={s.indent ?? 0}>
                <Box borderStyle="round" borderDimColor paddingX={1}>
                  <Markdown text={s.drawn} />
                </Box>
                <Box
                  position="absolute"
                  top={0}
                  left={0}
                  right={0}
                  bottom={0}
                  display="none"
                  backgroundColor="userMessageBackground"
                  hover={{ scope, display: 'flex' }}
                >
                  <Box flexGrow={1} borderStyle="round" paddingX={1}>
                    <Markdown text={s.drawn} />
                  </Box>
                </Box>
                <Box flexDirection="row" marginBottom={-1} paddingX={2}>
                  <Box flexGrow={1} width={0} marginRight={1}>
                    {name !== undefined && (
                      <Text dimColor wrap="truncate-end">
                        {' '}
                        {name}{' '}
                      </Text>
                    )}
                  </Box>
                  {s.code !== '' && (
                    <Button
                      key={`${e.requestId}:copy:${i}`}
                      label={LABEL}
                      plain
                      dimColor
                      hover={{ scope, dimColor: false, inverse: false, backgroundColor: 'userMessageBackground' }}
                      onPress={copy}
                    />
                  )}
                </Box>
              </Box>
            </Box>
          )
        })}
      </Box>
    )
  })
}
