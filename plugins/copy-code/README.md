# copy-code

A Claude Code mod that frames every code block in Claude's replies in a rounded box. The block's language is named on the left of the top border and a copy button sits on its right:

```
╭─ python ───────────────────────── ⧉ copy ─╮
│ def greet(name: str) -> str:              │
│     return f"hello {name}"                │
╰───────────────────────────────────────────╯
```

Hovering the button lights the whole block. Clicking it copies the code without the fences.

## Terminal only

This mod is for Claude Code running in a terminal. In the Desktop app, VS Code or the web it does nothing, and code blocks keep Claude Code's own look.

## Requirements

- Claude Code 2.1.287 or newer.
- A [Nerd Font](https://www.nerdfonts.com/) in your terminal, for the copy icon.
- Mouse support for hover and click. The fullscreen layout (`"tui": "fullscreen"`) has it.

## Try it

```sh
claude --plugin-dir path/to/copy-code
```

## Notes

- Languages appear by their full name: `py` shows as `python`, `md` as `markdown`. A name it doesn't know appears as written.
- Syntax colours come from Claude Code's highlighter. Languages it has no grammar for, such as fish, zig, lean and typst, appear as plain text.
