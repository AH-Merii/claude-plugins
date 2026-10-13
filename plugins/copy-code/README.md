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

- In the terminal, the mod adds a short note to Claude's system prompt asking it to give every code block a language, so a sketch that isn't valid code on its own still gets a name and colours. Print mode and the Desktop app don't get the note.
- Languages appear by their full name: `py` shows as `python`, `md` as `markdown`. A name it doesn't know appears as written.
- Code is coloured as in Claude Code's own code blocks. Languages it has no grammar for, such as fish, zig, lean and typst, appear as plain text.
- On Wayland, after Claude Code's own copy, the mod runs `wl-copy --type 'text/plain;charset=utf-8'`, so the clipboard holds the code as text. Claude Code's copy lets `wl-copy` guess the type, so a one-letter block can land as binary data and HTML as rich text. Claude Code's copy still fills the primary selection, a tmux buffer and the terminal's clipboard. Over SSH, without a Wayland display, or when `wl-copy` is missing or fails, only Claude Code's copy runs.
- In a narrow terminal a long language name is shortened, and left out when there is no room for it. Below 12 columns the mod steps aside and Claude Code draws the reply.
