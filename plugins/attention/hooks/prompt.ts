import type { Category, OpenItem } from '../types'
import { RESOLVED } from './categories'

// What Claude is told, built from the categories so a configured one is explained like a default.
export function instructions(categories: readonly Category[]): string {
  const pinned = categories.filter(c => c.pin).map(c => c.id)
  const example = pinned[0] ?? categories[0]?.id ?? 'decide-now'
  return [
    'The user skims your replies, and misses what sits in the middle of them. The attention mod draws tagged ' +
      'lines in colour at the end of each reply, so anything the user must read, decide or do goes there.',
    '',
    'End the reply with one line per item, each a blockquote led by its tag:',
    '',
    `> [!${example}] D3: Merge #41 as is, or clean up first?`,
    '',
    'The tags:',
    ...categories.map(c => `- \`${c.id}\`: ${c.meaning}.`),
    '',
    'Rules:',
    '- One short line per item. The detail belongs in the reply above; the line names the point.',
    '- Ask each choice as a question ending in "?", one choice per item. Order items so that the ones others ' +
      'depend on come first, and say so on the dependent one: "(after D2)".',
    `- Give every item the user may answer an id: D1, D2, … counting up through the session, never reused. ${
      pinned.length > 0 ? `${pinned.map(p => `\`${p}\``).join(' and ')} items stay pinned above the prompt until ` : ''
    }you mark them settled.`,
    `- When the user settles an item, or it no longer applies, add \`> [!${RESOLVED}] D3: <what was decided>\`. ` +
      'The user may answer in prose or ask about an item first; an item they only asked about stays open.',
    '- Raise each item once. Restate an earlier one only when it changed, under the same id: repeated lines ' +
      'turn into wallpaper the user stops reading, and pinned items are already shown above the prompt.',
    '- A default you are acting on says what you chose and the words that overrule it ("Say X to change it"); ' +
      'never "unless you say otherwise".',
    '- Leave the block out when there is nothing for the user. Never put the tags inside code blocks.',
  ].join('\n')
}

// The note beside each prompt while items are pinned, so they survive a compaction and Claude can close them.
export function reminder(open: readonly OpenItem[]): string {
  return [
    'attention: these items are still open, pinned above the prompt:',
    ...open.map(o => `- ${o.id} [${o.tag}] ${o.text}${o.suggestion ? ` Your suggestion: ${o.suggestion}` : ''}`),
    `If this message settles one, end your reply with \`> [!${RESOLVED}] <id>: <what was decided>\` for it.`,
  ].join('\n')
}
