---
name: attention
description: Configure the attention mod, which colours the lines at the end of Claude's replies that need the user (must-know, decide now, decide later, defaults, your actions, optional) and pins open decisions above the prompt. Use when the user wants to change a category's colour or label, add, rename or turn off a category, change what gets pinned, or reset attention to its defaults.
---

# Configuring attention

The config is one JSON file, `attention.json`, in Claude Code's config directory: `$CLAUDE_CONFIG_DIR/attention.json`, or `~/.claude/attention.json` when that variable is unset. Find the directory with `echo "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"`.

With no file, the defaults apply. The file holds only what differs from them, so write the smallest change that does what the user asked:

```json
{
  "categories": {
    "decide-now": { "color": "#ff5f00" },
    "optional": { "enabled": false },
    "ci-red": { "label": "CI RED", "color": "red", "meaning": "a check that failed and blocks the merge", "pin": true }
  }
}
```

Each key under `categories` is a category id: lowercase letters, digits and dashes (`resolved` is taken).

- **A default's id** changes only the fields given. The defaults are `must-know`, `decide-now`, `decide-later`, `suggestion`, `proceeding-with`, `your-action` and `optional`; their meanings are the tags listed in the attention section of your system prompt. The old ids `suggest` and `default` still reach `suggestion` and `proceeding-with`; write the new ids.
- **`"enabled": false`** turns a category off. Claude stops using its tag.
- **A new id** adds a category after the defaults. It needs `label`, `color` and `meaning`.

The fields:

| Field | Type | What it does |
| --- | --- | --- |
| `label` | string | The word drawn beside each line, e.g. `DECIDE NOW`. |
| `color` | string | A colour name (`red`, `cyan`), a hex colour (`#ff8700`), or a Claude Code theme key that follows the user's theme (`error`, `warning`, `success`, `suggestion`, `inactive`, `subtle`). |
| `meaning` | string | When Claude uses the tag. It is read as "the tag is for …", so write it as a noun phrase: "a choice you need before you can finish the current task". |
| `pin` | boolean | Keep the item in the band above the prompt until Claude marks it settled. Defaults pin `decide-now` and `decide-later`. `suggestion` items are never pinned on their own: each shows under the open decision it names. |
| `dim` | boolean | Draw the line dim, for items the user may skip. |
| `tint` | boolean | Draw the item's text in a dimmer shade of the category's colour, with code spans bold in the full colour. Needs a colour name or hex; with a theme key the text is drawn grey. Named colours are shaded from the values Claude Code's dark theme draws them in. On by default; set `false` to draw a category's text plain. |
| `enabled` | boolean | `false` turns the category off. |

## Steps

1. Read the file if it exists, and keep what is already there.
2. Make the change, then check the file is valid JSON (`jq . <file>`).
3. Tell the user it applies from their next message. The mod re-reads the file on each request.

If an entry can't be used (an unknown field, a wrong type, a new category missing a field), the mod names it in a toast and applies the rest. To reset to the defaults, delete the file.
