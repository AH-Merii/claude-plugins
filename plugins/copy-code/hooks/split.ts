export type Segment =
  | { kind: 'prose'; text: string }
  | { kind: 'code'; text: string; code: string; language?: string; indent?: number }

// A backtick fence's info string may hold no backtick (CommonMark); a tilde fence's may.
const OPEN = /^( {0,3})(`{3,}(?!.*`)|~{3,})\s*([^\s`]*)/

// Splits markdown into prose and fenced code blocks, each code block keeping its fences.
export function split(text: string): Segment[] {
  const lines = text.split('\n')
  const segments: Segment[] = []
  let prose: string[] = []
  let i = 0

  const flush = () => {
    if (prose.join('').trim() !== '') {
      segments.push({ kind: 'prose', text: prose.join('\n') })
    }
    prose = []
  }

  while (i < lines.length) {
    const line = lines[i] ?? ''
    const open = OPEN.exec(line)
    const fence = open?.[2]
    if (!fence) {
      prose.push(line)
      i++
      continue
    }

    const close = new RegExp(`^ {0,3}${fence[0] === '`' ? '`' : '~'}{${fence.length},}\\s*$`)
    let end = i + 1
    while (end < lines.length && !close.test(lines[end] ?? '')) end++

    flush()
    // As CommonMark does: up to the fence's own indent comes off each code line.
    const indent = open?.[1]?.length ?? 0
    const body = lines.slice(i + 1, end).map(l => l.replace(new RegExp(`^ {0,${indent}}`), ''))
    const segment: Segment = { kind: 'code', text: lines.slice(i, end + 1).join('\n'), code: body.join('\n') }
    if (open?.[3]) {
      segment.language = open[3]
    }
    if (indent > 0) {
      segment.indent = indent
    }
    segments.push(segment)
    i = end + 1
  }

  flush()
  return segments
}
