import type { Register } from 'claude-code'

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
// Narrower than this a box can't hold its corners and copy, so Claude Code draws the reply.
const MIN_COLUMNS = 12
// How long a toast stays; Claude Code's default.
const TOAST_MS = 4000

export const register: Register = on => {
  // The toast showing, if any. Raising another relays out the transcript, which can drop a press in flight.
  let toast = { text: '', until: 0 }

  on('ui.render', { component: 'AssistantMessage', surface: 'terminal' }, ($, e, next) => {
    const segments = split(e.props.text)
    const isDrawable = segments.some(s => s.kind === 'code') && segments.every(s => s.text.length <= MAX)

    const columns = e.viewport?.columns
    if (!isDrawable || (columns !== undefined && columns < MIN_COLUMNS)) {
      return next(e)
    }

    const { Box, Button, Code, Markdown, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {segments.map((s, i) => {
          if (s.kind === 'prose') {
            return <Markdown key={`${e.requestId}:${i}`} text={s.text} />
          }

          const copy = async () => {
            const result = await $.ui.copy({ text: s.code, surface: 'terminal' })
            const text = result.isCopied ? 'Copied' : `Copy failed: ${result.reason}`
            const now = await $.clock.now()
            if (text !== toast.text || now >= toast.until) {
              toast = { text, until: now + TOAST_MS }
              $.ui.toast(text, { timeoutMs: TOAST_MS })
            }
          }

          // Not the wrapper's key: a keyed Box is a scope of its own, and hovering the code would join it.
          const scope = `${e.requestId}:${i}:lit`
          // The name's cells: the box less its left corner, the right side and a space either side.
          const room = columns === undefined ? Infinity : columns - (s.indent ?? 0) - 2 - RIGHT - 2
          // Drawn in both layers so it is lit with the box without joining the hover group.
          const tag = s.language && room >= MIN_NAME && (
            <Box position="absolute" top={0} left={2} right={RIGHT}>
              <Text dimColor wrap="truncate-end">
                {' '}
                {languageName(s.language)}{' '}
              </Text>
            </Box>
          )

          // The overlay redraws the whole box lit, so hovering the code lights nothing; the label is drawn last, over the top border.
          return (
            <Box key={`${e.requestId}:${i}`} flexDirection="column" marginBottom={1} marginLeft={s.indent ?? 0}>
              <Box borderStyle="round" borderDimColor paddingX={1}>
                <Code source={s.code} language={s.language} />
              </Box>
              {tag}
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
                  <Code source={s.code} language={s.language} />
                </Box>
                {tag}
              </Box>
              {s.code !== '' && (
                <Box position="absolute" top={0} right={2}>
                  <Button
                    key={`${e.requestId}:copy:${i}`}
                    label={LABEL}
                    plain
                    dimColor
                    hover={{ scope, dimColor: false, inverse: false, backgroundColor: 'userMessageBackground' }}
                    onPress={copy}
                  />
                </Box>
              )}
            </Box>
          )
        })}
      </Box>
    )
  })
}
