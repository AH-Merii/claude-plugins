# attention

A Claude Code mod for people who skim replies. Claude ends each reply with one tagged line for each thing that needs you, and the mod draws those lines in colour. Decisions stay pinned above the prompt until they're settled.

```text
● Merged #72; CI is green. Next I start on slice 16.

  ▌ MUST KNOW    The Outlook wizard never ran against a real account.
  ▌ DECIDE NOW   D4 File both issues as drafted?
  ▌ DECIDE LATER D5 Go past slice 15? (after D4)
  ▌ DEFAULT      D6 Classifying runs only when asked. Say so to turn it on in the background.
  ▌ YOUR ACTION  Run ! rm -rf ~/.azure
  ▌ OPTIONAL     Want me to close the stale issues?
```

## Why

An audit of 14 sessions of skimmed replies found four patterns:

- Asks were missed when they sat in the middle of a long reply, or when several were stacked. Asks phrased as statements ("unless you say otherwise", "tell me if…") were also missed.
- A default Claude acted on "unless you say otherwise" shipped, and needed a PR to undo.
- Questions asked just before a task notification or a `/compact` were lost.
- Users asked about things the reply had already said, in a middle bullet.

So the mod asks Claude for these things:

- Put everything that needs you at the end, one short line per item.
- Ask each choice as a question.
- Give every item you may answer an id, such as `D4`. You can then reply "D4: why not X?" in prose and ask about an item before you answer it.

Pinned items carry over to Claude with each message you type, so a `/compact` doesn't lose them. Each one stays above the prompt until Claude marks it settled, or until you dismiss it with its `✕`.

## Categories

| Tag | Colour | Pinned | For |
| --- | --- | --- | --- |
| `must-know` | red | | A risk, a surprise, a change you didn't ask for, or work that was skipped, unverified or failed |
| `decide-now` | orange | yes | A choice the current task needs |
| `decide-later` | yellow | yes | A choice a later task needs |
| `default` | magenta | | A choice Claude made and acts on unless you overrule it |
| `your-action` | cyan | | Something only you can do: run a command, sign in, restart something |
| `optional` | dim | | An offer or a nice-to-know you can skip |

## Configuring

Ask Claude to change it, e.g. "make decide-now red" or "add a category for failed CI checks". The `attention` skill edits `attention.json` in Claude Code's config directory (`$CLAUDE_CONFIG_DIR`, or `~/.claude`). The file holds only what differs from the defaults:

```json
{
  "categories": {
    "decide-now": { "color": "#ff5f00" },
    "optional": { "enabled": false },
    "ci-red": { "label": "CI RED", "color": "red", "meaning": "a check that failed and blocks the merge", "pin": true }
  }
}
```

The fields are `label`, `color`, `meaning`, `pin`, `dim`, `tint` (the item's text in a dimmer shade of the label's colour, on by default) and `enabled`. A colour is a name, a hex value, or a Claude Code theme key. Changes apply from your next message. If an entry can't be used, a toast names it and the rest still apply.

## Terminal only

The colours and the band are drawn in the terminal. In print mode, the Desktop app or VS Code, Claude isn't asked for the tags, so replies read as before.

## With copy-code

Both mods draw replies. With `attention` outside `copy-code`, code boxes and coloured lines show together. If the order is reversed, a reply that holds code shows its attention lines as plain quotes. The band works either way.

## Install

```text
/plugin install attention --marketplace AH-Merii/claude-plugins
```
