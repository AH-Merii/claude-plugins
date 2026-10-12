# vim-ux

A Claude Code mod for its vim mode (`"editorMode": "vim"`). It gives the prompt a cursor that shows the mode, and a Ctrl+C that only clears what you typed:

- A steady bar cursor in INSERT, and a steady block in NORMAL and VISUAL. On exit the terminal's own cursor comes back.
- Ctrl+C clears the prompt and does nothing else. It never exits and never stops a running turn; Esc stops a turn. While Claude is working you can clear a draft and the reply carries on.

Ctrl+U and Ctrl+D scroll the chat half a page. That part needs no mod, only the keybindings below.

## Terminal only

This mod is for Claude Code running in a terminal. In the Desktop app, VS Code or the web it does nothing.

## Requirements

- Claude Code 2.1.289 or newer.
- Vim mode on: `"editorMode": "vim"` in `settings.json`, or `/config`. Outside vim mode the mod leaves the cursor alone, and if you turn vim mode off mid-session the terminal's own cursor comes back.
- The `-- INSERT --` label shown below the prompt. The mod reads the mode from it, so with `"hideVimModeIndicator": true` in your `statusLine` setting it can't tell the modes apart and leaves the cursor alone.
- A terminal that draws DECSCUSR cursor shapes, such as Ghostty.

## Setup

The mod can't change your settings or keybindings, so add these yourself.

1. In `settings.json`, let Claude Code show the terminal's real cursor. Without it Claude Code hides the cursor and draws its own, so the shapes never show. It applies when Claude Code starts.

   ```json
   {
     "env": { "CLAUDE_CODE_NATIVE_CURSOR": "1" }
   }
   ```

2. In `keybindings.json`, next to `settings.json`, bind the keys:

   ```json
   [
     { "context": "Scroll", "bindings": { "ctrl+u": "scroll:halfPageUp", "ctrl+d": "scroll:halfPageDown" } },
     { "context": "Chat", "bindings": { "ctrl+c": "command:vim-ux-clear" } }
   ]
   ```

   Claude Code logs "Cannot be rebound … (hardcoded)" for ctrl+c and ctrl+d, but the bindings work.

## Try it

```sh
claude --plugin-dir path/to/vim-ux
```

## Defaults it overrides

With the keybindings above:

- **Ctrl+U** no longer deletes back to the start of the line. `d0` does that in NORMAL.
- **Ctrl+D** no longer deletes the character under the cursor in INSERT, and no longer starts an exit.
- **Ctrl+C** no longer exits, cancels the model picker or leaves the Ctrl+O view. Esc does those.
- `/exit` and `/quit` are the ways out.

If you turn the mod off but keep the Ctrl+C binding, Ctrl+C prints `Unknown command: /vim-ux-clear`.

## What a mod can't do

- **Colour the prompt by mode.** A mod gets no event when the vim mode changes, and the only way to repaint the prompt, filling it again, moves the vim cursor. So the prompt keeps one colour in every mode.
- **Catch Ctrl+C or Ctrl+D itself.** Claude Code handles exit on its own; only a `command:` binding takes the key first.
- **Scroll the chat.** That is what the `Scroll` keybindings are for.
