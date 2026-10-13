# niri-screen-lab reference

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
| chromium | the browser under test (`browse` only) | on `PATH`, with `preflight --browser` |
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
use. Both kinds of lab use the same app-id, so one rule places either.

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

## The browser lab

`lab.py browse URL` opens Chromium the way `start` opens Ghostty: the app-id is checked,
the window must turn up on the spare output, unfocused, and the same refusals apply. Then:

- **The profile is new each time.** It lives in `$XDG_CACHE_HOME/niri-screen-lab/profile`
  (on disk, not in the runtime tmpfs) and `stop` deletes it. So the page never sees the
  user's cookies, sign-ins or extensions. Downloads go to
  `$XDG_CACHE_HOME/niri-screen-lab/downloads` without asking, never to `~/Downloads`.
- **Chromium runs with these flags:**
  - `--class=dev.claude.lab`, which sets its Wayland app-id;
  - `--password-store=basic`, so it never opens the user's keyring;
  - `--deny-permission-prompts` and `--disable-notifications`, so no prompt or notification
    reaches the user's screen;
  - `--disable-blink-features=FileSystemAccessLocal`. `showOpenFilePicker()` and
    `showSaveFilePicker()` would open a portal dialog, which DevTools can't hold back.
    Without them, pages fall back to `<input type=file>`, which it can;
  - `--test-type`, which keeps Chromium's "unsupported command-line flag" bar (for the flag
    above) off the page, where it would shift the viewport;
  - `--remote-debugging-port=0`: a free port on 127.0.0.1, which Chromium writes to
    `DevToolsActivePort` in the profile.
- **The keeper holds file choosers back.** `browser.py keep` holds one DevTools session to
  the whole browser and asks every page for `Page.setInterceptFileChooserDialog`, since
  interception lasts only as long as the session that asked. A chooser then opens no dialog;
  it is logged to `filechooser.log`. The keeper exits with Chromium.
- **The viewport is measured.** A marker page puts a magenta square in each corner of the
  viewport; a screenshot finds them, which gives the viewport's place in a full shot and its
  scale. Then the lab goes to URL.
- **Input is refused while the window has focus.** niri lets only the client with keyboard
  focus set the clipboard or the primary selection: smithay logs "denying setting selection
  by a non-focused client" otherwise (`src/wayland/selection/data_device/device.rs` and
  `primary_selection/device.rs`). Input through DevTools reaches the page without focus, so
  an unfocused lab can click and type freely, and nothing the page does can write the
  user's clipboard. With focus (a pointer on the spare screen) that no longer holds, so
  `keys`, `key`, `hover`, `click`, `scroll`, `open` and `js` refuse.

Browser input:

- `keys` types text with `Input.insertText`, and presses `\r`, `\t`, `\e` and backspace as
  keys.
- `key` takes the names below plus any single character, with `ctrl-`, `alt-`, `shift-` and
  `meta-` in front (`ctrl-a`, `ctrl-shift-p`, `shift-1`). A shortcut types no text.
- `hover`, `click` and `scroll` take the page's CSS pixels, `X Y` from the viewport's top
  left. `cell X Y [--crop]` maps a screenshot pixel to them. `js` can give an element's
  position directly:
  `lab.py js "(r => [r.x + r.width/2, r.y + r.height/2])(document.querySelector('button').getBoundingClientRect())"`.
- `js` runs an expression with `awaitPromise`, so `fetch(...).then(...)` works, and prints
  its JSON value. A thrown error is reported as one.

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

This section is about the terminal lab; a browser lab's coordinates are above.

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
- wf-recorder records a frame only when the screen changes. A still screen gives one frame,
  which can't become a GIF, so `rec-stop` refuses; take a `shot` instead. A terminal's
  blinking cursor is enough motion; a still web page isn't.

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

- `state.json`: pid, output, grid, any recording, and the owning session;
- `feed`: the FIFO;
- `size`;
- `osc52.log`;
- `relay.log` and `ghostty.log`, for when the window closes unexpectedly;
- a browser lab's `chromium.log`, `keeper.log` and `filechooser.log`. Its profile and
  downloads are in `$XDG_CACHE_HOME/niri-screen-lab/`.

Only one lab runs at a time. `start` holds `lock` while it checks the spare output and opens
the window, so two sessions starting at once can't both get through.

The lab's owner is the session's `$CLAUDE_PID`, the `claude` process. While that process
is alive, every command except `preflight` refuses another session, `stop` included. Once
it has exited, any session may drive or stop the lab, so a lab left behind never blocks the
next one. Subagents share their parent's `claude` process, so they share its lab too.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `start` aborted: window on the wrong output | the rule is missing, or names another output; rerun `preflight` |
| refused: `belongs to another Claude session` | another session is using the lab; retry later or ask the user. Never stop it |
| `no lab is running` right after start | the command exited; read `relay.log` and `ghostty.log` |
| `shot` refuses: other windows share the workspace | ask the user to move them, or to switch the spare output to an empty workspace |
| warning: the lab window has focus | the pointer is on the spare screen; ask the user to move it |
| `cell` refuses: resized | the user changed the column width; restart the lab |
| keys do nothing | the app is in kitty keyboard mode and wants CSI-u; send them with `keys` |
| browser input refused: the window has focus | the pointer is on the spare screen; ask the user to move it |
| `rec-stop` refuses: ffmpeg could not make the GIF | nothing moved while recording; drive the page during the recording, or take a `shot` |
| a page's file upload does nothing | the lab held the chooser back (`filechooser.log`); load the content with `js` instead |
