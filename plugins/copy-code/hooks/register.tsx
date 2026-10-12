import type { Register } from 'claude-code'

import { languageName } from './languages'
import { split } from './split'

const MAX = 10000

// nf-fa-copy, from a Nerd Font.
const ICON = '\uF0C5'

export const register: Register = on => {
  on('ui.render', { component: 'AssistantMessage', surface: 'terminal' }, ($, e, next) => {
    const segments = split(e.props.text)
    const isDrawable = segments.some(s => s.kind === 'code') && segments.every(s => s.text.length <= MAX)

    if (!isDrawable) {
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
            $.ui.toast(result.isCopied ? 'Copied' : `Copy failed: ${result.reason}`)
          }

          // Not the wrapper's key: a keyed Box is a scope of its own, and hovering the code would join it.
          const scope = `${e.requestId}:${i}:lit`
          // Drawn in both layers so it is lit with the box without joining the hover group.
          const tag = s.language && (
            <Box position="absolute" top={0} left={2}>
              <Text dimColor> {languageName(s.language)} </Text>
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
                    label={` ${ICON} copy `}
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
