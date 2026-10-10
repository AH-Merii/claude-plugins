# screen-lab reference

## Prerequisites

`lab.py preflight` checks each of these and prints what to ask the user when one is missing.

| Need | Why | Check |
|------|-----|-------|
| niri, reachable with `niri msg` | window placement, window lookup, output geometry | `NIRI_SOCKET` set, `niri msg version` |
| 2+ enabled outputs | one the user works on, one spare | `niri msg outputs` |
| a spare output | where the lab lives | `SCREEN_LAB_OUTPUT`, else an unfocused `eDP-*` (the laptop panel), else the only unfocused output; refused if the user is focused on it |
| an empty visible workspace on it | captures take the whole output | `niri msg windows` |
| a niri window rule | opens the lab there, unfocused | parsed from the niri config, includes followed |
| a valid GTK app-id | Ghostty silently ignores an invalid `--class` | `Gio.Application.id_is_valid` (needs python3 + PyGObject) |
| ghostty | the terminal under test | on `PATH` |
| grim | screenshots that never touch the clipboard | on `PATH` |
| wf-recorder, ffmpeg | GIFs: record, then palettegen/paletteuse | on `PATH` |
| `$XDG_RUNTIME_DIR` | runtime state in `$XDG_RUNTIME_DIR/screen-lab/` | exists |

The window rule is the one user-specific part. The output name belongs to their setup.
Preflight prints the exact block to add when it is missing, for example:

```kdl
window-rule {
    match app-id=r#"^dev\.claude\.lab$"#
    open-on-output "eDP-1"
    open-focused false
}
```

Use a raw string `r#"..."#` for the regex. A `\.` inside a normal KDL string is a parse
error, and niri then keeps running on the old config. Check with `niri validate`. niri
reloads the file when it is saved.

Overrides: `SCREEN_LAB_OUTPUT=<name>` chooses the spare output, and `SCREEN_LAB_APP_ID`
changes the app-id (default `dev.claude.lab`). The rule must match whichever app-id you
use.

## What start does, and why

- **The app-id is checked before launch.** `claude-lab` was once silently ignored, and the
  window opened focused on the user's main screen.
- **The window is found by Ghostty's pid,** not its app-id, so a wrong app-id can't hide
  it. It must turn up on the spare output, with the right app-id, unfocused. Otherwise
  Ghostty is killed and start aborts.
- **The environment is cleaned.** All `CLAUDE*` variables except `CLAUDE_CONFIG_DIR` are
  removed, along with `TMUX` and `TMUX_PANE`. Otherwise a lab `claude` inherits
  `CLAUDE_CODE_CHILD_SESSION` and shows "Transcript saving is off".
- **The command gets no display.** The relay drops `WAYLAND_DISPLAY`, `WAYLAND_SOCKET` and
  `DISPLAY` for the command. Apps that copy through `wl-copy` (Claude Code's `ui.copy`
  does) then fall back to OSC 52.
- **Ghostty runs with these flags:**
  - `--clipboard-write=deny` and `--clipboard-read=deny`, so OSC 52 never reaches the
    clipboard;
  - `--copy-on-select=false`;
  - `--desktop-notifications=false`, so the app can't pop notifications on the user's
    screen;
  - `--confirm-close-surface=false` and `--gtk-single-instance=false`.

  The rest of the user's Ghostty config (font, theme) applies, so what you see is what
  they get.
- **The grid is measured.** Before the command starts, the relay paints a magenta cell in
  the top-left and bottom-right corners. start screenshots them to find the grid origin
  and the cell size, then clears the screen and runs the command.

## Input

The relay is a pty between Ghostty and the command. Bytes written to
`$XDG_RUNTIME_DIR/screen-lab/feed` are merged into the command's input as if typed.
Nothing goes through the compositor, so the user's focused window can never receive them.

- `keys` sends raw bytes. Escapes: `\e`, `\xHH`, `\NNN` (octal), `\uXXXX`, `\r`, `\n`, `\t`.
  Use `\r` for Enter.
- `key` sends named keys: `enter esc tab backspace space up down left right home end pgup
  pgdn delete shift-tab shift-enter ctrl-X alt-X`. They use legacy encodings, except
  `shift-enter`, which is kitty-protocol `\e[13;2u`. An app in kitty keyboard mode may want
  CSI-u forms for other modified keys. Send those with `keys`.
- Mouse events are SGR. The app must have turned on mouse tracking, as Claude Code does:
  - move: `\e[<35;COL;ROWM`
  - press: `\e[<0;COL;ROWM`, release: `\e[<0;COL;ROWm` (middle button 1, right 2)
  - wheel: 64 up, 65 down

  `hover`, `click` and `scroll` build these for you. Columns and rows are 1-based.

## Mouse coordinates

`lab.py info` shows `grid`: the origin `x,y` in a full-output screenshot, plus `cell_w`,
`cell_h`, `cols` and `rows`.

- In a `--crop` shot the origin is `0,0`, so `col = floor(x / cell_w) + 1` and
  `row = floor(y / cell_h) + 1`.
- In a full shot, subtract the origin first.

`lab.py cell X Y [--crop]` does this. To aim, find the label in the screenshot, take a pixel
in the middle of it, map that pixel, and hover. Then check with a new shot. `cell` refuses
once the window has been resized since start. Restart the lab to measure again.

The size the terminal reports (TIOCGWINSZ: cols, rows, pixels) stays current in
`$XDG_RUNTIME_DIR/screen-lab/size`.

## Captures

- `shot FILE [--crop]` uses `grim -o <output>` or `grim -g <grid rect>`, and never
  includes the cursor.
- `gif FILE SECONDS [--crop] [--fps 12] [--width 1200]` records with wf-recorder, then
  converts with ffmpeg (palettegen, then paletteuse). A `--crop` GIF of about 3 s is
  roughly 200 KB.
- `rec-start [--crop]` and `rec-stop FILE` do the same with no fixed length.

niri reports no position for tiled windows (`tile_pos_in_workspace_view` is null), so a
capture is always of the whole output. `--crop` cuts out the grid that start measured.
That is why every capture first checks that:

- the lab window is on the spare output,
- its workspace is the visible one,
- and no other window shares it.

A recording is checked again when it stops, and thrown away if that check fails.
Layer-shell surfaces (the bar, notifications) still show in full-output shots.

## Clipboard

Ghostty denies OSC 52 writes, and the command has no Wayland or X display. Instead, the
relay logs every OSC 52 write the app makes, decoded, to
`$XDG_RUNTIME_DIR/screen-lab/osc52.log`. Check that file to test a copy feature. In
testing, the copy-code mod's click logged its text there and showed "Copied". The user's
clipboard stayed untouched.

## Images

Ghostty shows kitty-graphics images only when no tmux sits in between. The lab runs the
command directly, so this is the place to test inline images.

## Claude Code in the lab

```bash
lab.py start --cwd ~/project -- claude --model haiku \
  --plugin-dir /path/to/mod --resume <test-session-id> --fork-session
```

- Run it in the project directory the session belongs to. Otherwise `--resume` can't find
  the session, and Claude Code may ask about external CLAUDE.md imports.
- `--fork-session` leaves the test session unchanged, so every run starts from the same
  content.
- Never pass the live session's id (`$CLAUDE_CODE_SESSION_ID`).

## State

All of it lives in `$XDG_RUNTIME_DIR/screen-lab/`:

- `state.json`: pid, output, grid, any recording;
- `feed`: the FIFO;
- `size`;
- `osc52.log`;
- `relay.log` and `ghostty.log`, for when the window closes unexpectedly.

Only one lab runs at a time.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `start` aborted: window on the wrong output | the rule is missing, or names another output; rerun `preflight` |
| `no lab is running` right after start | the command exited; read `relay.log` and `ghostty.log` |
| `shot` refuses: other windows share the workspace | ask the user to move them, or to switch the spare output to an empty workspace |
| warning: the lab window has focus | the pointer is on the spare screen; ask the user to move it |
| `cell` refuses: resized | the user changed the column width; restart the lab |
| keys do nothing | the app is in kitty keyboard mode and wants CSI-u; send them with `keys` |
