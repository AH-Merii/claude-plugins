# niri-screen-lab reference

## Prerequisites

`lab.py preflight` checks each of these and prints what to ask the user when one is missing.

| Need | Why | Check |
|------|-----|-------|
| niri, reachable on `$NIRI_SOCKET` | window placement and lookup, ScreenCast | `NIRI_SOCKET` set, a `Version` request |
| an output for lab windows | where their hidden workspaces go | one enabled output (single-screen mode), or of 2+: `SCREEN_LAB_OUTPUT`, else an unfocused `eDP-*` (the laptop panel), else the only unfocused output; refused if the user is focused on it |
| a niri window rule, with 2+ outputs | opens lab windows on that output, unfocused | parsed from the niri config, includes followed |
| a valid GTK app-id | Ghostty silently ignores an invalid `--class` | `Gio.Application.id_is_valid` (needs python3 + PyGObject) |
| ghostty | the terminal under test | on `PATH` |
| chromium | the browser under test (`browse` only) | on `PATH`, with `preflight --browser` |
| gdbus | terminal capture through niri's `org.gnome.Mutter.ScreenCast` | on `PATH` (glib2) |
| gst-launch-1.0 with `pipewiresrc` and `vapostproc` | decoding a terminal lab's cast to PNG | on `PATH` (gstreamer, gst-plugin-pipewire, gst-plugin-va) |
| ffmpeg | GIFs: palettegen, then paletteuse | on `PATH` |
| `$XDG_RUNTIME_DIR` | each lab's state in `$XDG_RUNTIME_DIR/screen-lab/<id>/` | exists |

Preflight also prints `MemAvailable` and what labs typically cost; see Memory below.

With two or more outputs, the window rule is the one user-specific part. The output name
belongs to their setup. Preflight prints the exact block to add when it is missing, for
example:

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

Overrides: `SCREEN_LAB_OUTPUT=<name>` chooses the output, and `SCREEN_LAB_APP_ID` changes
the app-id (default `dev.claude.lab`). The rule must match whichever app-id you use. Both
kinds of lab use the same app-id, so one rule places either.

## Several labs, and `--lab`

Any number of labs run at once, from one session or several, terminal or browser, in any
mix. `start` and `browse` print `lab <id>`, and every command that acts on a lab requires
`--lab <id>`. There is no "the only lab" default: subagents share their parent's
`CLAUDE_PID`, so a default could pick a sibling's lab. `preflight`, `list`, `start` and
`browse` take no id.

`list` prints one line per lab: id, kind, owner (its `CLAUDE_PID`, live or ended), output,
workspace name, and whether its app is alive.

## Where lab windows go

Every lab window lives on a workspace of its own, `claude-lab-<id>`, on the chosen output.
It is never the visible workspace, so the user never sees it, and focus-follows-mouse can't
reach it. A headless browser lab has no window and no workspace.

Placement runs under one global lock (`$XDG_RUNTIME_DIR/screen-lab/lock`), so two labs
opening at once can't take the same workspace:

1. Open niri's event stream (an `"EventStream"` request on `$NIRI_SOCKET`) before launching,
   so the window's opening can't be missed.
2. Launch the app.
3. On the first `WindowOpenedOrChanged` with the lab's app-id and the launched pid, read the
   workspaces again and take the one with the highest `idx` on the chosen output. niri
   keeps that one empty and unnamed.
4. `MoveWindowToWorkspace` with `reference: {"Id": …}` and `focus: false`.
5. `SetWorkspaceName` `claude-lab-<id>` on that workspace, by id.
6. Check that the window is on it, the workspace has the name, and the window isn't focused.
   On any failure the window is closed, the name dropped, and the command refuses.

Why it works this way:

- **No index references.** niri resolves an index against the focused output, which is the
  user's.
- **No cached workspace ids.** niri deletes a workspace once it is empty and inactive, and
  another client's window can change the layout at any time, so every step reads again.
- **Every action is checked.** niri answers `{"Ok":"Handled"}` even when an action did nothing
  (an unknown id, a name already taken).
- **The window is found by the launched pid,** not only its app-id, so another lab's window
  changing at the same moment can't be taken for it.

**Single-screen mode.** With one enabled output there is nowhere else for the window to
open, so no rule is needed. niri gives the new window focus until it moves, for about 50 ms.
Before launching, `start` and `browse --window` print: "Tell the user: the new lab window
holds keyboard focus for about 50 ms before it moves to a hidden workspace; a key pressed
then goes to the lab." Relay it.

## What start does, and why

- **The app-id is checked before launch.** `claude-lab` was once silently ignored, and the
  window opened focused on the user's main screen.
- **The environment is cleaned.** All `CLAUDE*` variables except `CLAUDE_CONFIG_DIR` are
  removed, along with `TMUX` and `TMUX_PANE`. Otherwise a lab `claude` inherits
  `CLAUDE_CODE_CHILD_SESSION` and shows "Transcript saving is off". So are
  `XDG_ACTIVATION_TOKEN` and `DESKTOP_STARTUP_ID`: with the session's token, the app could ask
  niri to activate its window and take the user's focus.
- **The command gets no display.** The relay drops `WAYLAND_DISPLAY`, `WAYLAND_SOCKET` and
  `DISPLAY` for the command. Apps that copy through `wl-copy` (Claude Code's `ui.copy`
  does) then fall back to OSC 52.
- **Ghostty runs with these flags:**
  - `--clipboard-write=deny` and `--clipboard-read=deny`, so OSC 52 never reaches the
    clipboard;
  - `--copy-on-select=false`;
  - `--desktop-notifications=false`, so the app can't pop notifications on the user's
    screen;
  - `--gtk-single-instance=false`, so each lab is its own Ghostty process, found by its pid;
  - `--confirm-close-surface=false`.

  The rest of the user's Ghostty config (font, theme) applies, so what you see is what
  they get.
- **The grid is measured.** Before the command starts, the relay paints a magenta cell in
  the top-left and bottom-right corners. start finds them in a frame of the window's cast,
  which gives the grid origin and the cell size, then lets the relay clear the screen and
  run the command. The cast shifts the colours a few levels (`#232831` for `#282c34`), so
  the match has a tolerance.

## The browser lab

`lab.py browse URL` runs Chromium headless (`--headless=new`) in a 1280x800 window: no window
on screen, no workspace, no placement. `lab.py browse --window URL` opens the real window, placed like a terminal lab's.
Every browser command works the same in both modes, because input and capture go through
DevTools. Then:

- **The profile is new for each lab.** It lives in `$XDG_CACHE_HOME/niri-screen-lab/<id>/`
  (on disk, not in the runtime tmpfs) and `stop` deletes it. So the page never sees the
  user's cookies, sign-ins or extensions. Downloads go to its `downloads/` without asking,
  never to `~/Downloads`.
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
- **The DevTools client refuses `Page.bringToFront` and `Target.activateTarget`,** and sends
  nothing for them: either could hand a windowed lab the user's focus.
- **The keeper holds file choosers back.** `browser.py keep` holds one DevTools session to
  the whole browser and asks every page for `Page.setInterceptFileChooserDialog`, since
  interception lasts only as long as the session that asked. A chooser then opens no dialog;
  it is logged to `filechooser.log`. The keeper exits with Chromium.
- **A windowed lab closes popups.** Only the lab's first window is placed on its hidden
  workspace, so a page that opens in a new browser window (`window.open` with popup
  features) would show, and could take focus, on the user's screen. The keeper asks
  `Browser.getWindowForTarget` for every page and closes, with `Target.closeTarget`, any
  page outside the first window. New tabs stay. A headless lab keeps its popups.
- **A windowed lab refuses input while its window has focus.** niri lets only the client
  with keyboard focus set the clipboard or the primary selection: smithay logs "denying
  setting selection by a non-focused client" otherwise
  (`src/wayland/selection/data_device/device.rs` and `primary_selection/device.rs`). Input
  through DevTools reaches the page without focus, so an unfocused lab can click and type
  freely, and nothing the page does can write the user's clipboard. With focus that no
  longer holds, so `keys`, `key`, `hover`, `click`, `scroll`, `open` and `js` refuse while
  any window of the lab has focus, a popup included. A headless lab has no window, so it
  can't have focus.

Browser input:

- `keys` types text with `Input.insertText`, and presses `\r`, `\t`, `\e` and backspace as
  keys.
- `key` takes the names below plus any single character, with `ctrl-`, `alt-`, `shift-` and
  `meta-` in front (`ctrl-a`, `ctrl-shift-p`, `shift-1`). A shortcut types no text.
- `hover`, `click` and `scroll` take the page's CSS pixels, `X Y` from the viewport's top
  left. `cell X Y` maps a screenshot pixel to them. `js` can give an element's position
  directly:
  `lab.py js "(r => [r.x + r.width/2, r.y + r.height/2])(document.querySelector('button').getBoundingClientRect())" --lab ID`.
- `js` runs an expression with `awaitPromise`, so `fetch(...).then(...)` works, and prints
  its JSON value. A thrown error is reported as one.

## Input

The relay is a pty between Ghostty and the command. Bytes written to the lab's `feed` FIFO
are merged into the command's input as if typed. Nothing goes through the compositor, so the
user's focused window can never receive them.

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

`lab.py info --lab ID` shows `grid`: the origin `x,y` in a shot of the window, plus `cell_w`,
`cell_h`, `cols` and `rows`.

- In a `--crop` shot the origin is `0,0`, so `col = floor(x / cell_w) + 1` and
  `row = floor(y / cell_h) + 1`.
- In a whole-window shot, subtract the origin first.

`lab.py cell X Y [--crop] --lab ID` does this. To aim, find the label in the screenshot, take
a pixel in the middle of it, map that pixel, and hover. Then check with a new shot. `cell`
refuses once the window has been resized since start. Restart the lab to measure again.

The size the terminal reports (TIOCGWINSZ: cols, rows, pixels) stays current in the lab's
`size` file.

## Captures

Nothing captures the screen: lab windows are on hidden workspaces, and a screenshot of an
output would show the user's windows and, with niri's screenshot actions, overwrite the
clipboard.

**A terminal lab** is captured through niri's `org.gnome.Mutter.ScreenCast` D-Bus service,
which niri itself provides, so no portal or dialog is involved and the window needs no
focus. With `gdbus`: `CreateSession({})`, then `RecordWindow({'window-id': <uint64 W>})`, then
`Start`. The cast's PipeWire node is the one `niri msg -j casts` lists for that window
(`target.Window.id`), and GStreamer decodes it:
`pipewiresrc path=NODE ! vapostproc ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=RGB ! pngenc`.
That is the only pipeline that worked with niri's dmabuf frames.

- niri draws a window on a hidden workspace about once a second (`src/niri.rs:189-192`), and
  a cast's first frame is that old. `shot` drops it and keeps the next one, so a shot taken
  after input shows a frame drawn after the input. A shot takes up to about 2 s.
- `shot FILE` is the whole lab window; `--crop` cuts out the grid that start measured.
- `gif FILE SECONDS [--crop] [--fps 12] [--width 1200]` records the cast, then converts with
  ffmpeg (palettegen, then paletteuse). It holds about one frame a second.
- `rec-start [--crop]` and `rec-stop FILE` do the same with no fixed length.
- A cast session outlives the process that created it, so each lab records its sessions in
  its `casts/` folder and stops every one on `rec-stop`, `stop` and in the sweep.

**A browser lab**, headless or windowed, is captured with DevTools' `Page.captureScreenshot`.

- `shot FILE` is the page's viewport, with or without `--crop`: a page has nothing around it.
- `gif` and `rec-start`/`rec-stop` poll screenshots (`browser.py poll`, about 10 a second),
  then ffmpeg assembles them. Two labs polling at once don't slow each other.

## Memory

`preflight`, `start` and `browse` print `MemAvailable` from `/proc/meminfo` and what labs
typically cost, measured on niri:

- about 80–110 MiB per terminal lab, plus about 50 MiB per running recording;
- about 280–300 MiB per headless browser lab, its keeper included;
- about 340–460 MiB per windowed browser lab.

There is no hard limit: whether to open another
lab is the agent's call, weighed against its task.

## Clipboard

Ghostty denies OSC 52 writes, and the command has no Wayland or X display. Instead, the
relay logs every OSC 52 write the app makes, decoded, to the lab's `osc52.log`. Check that
file to test a copy feature. In testing, the copy-code mod's click logged its text there and
showed "Copied". The user's clipboard stayed untouched.

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

Each lab keeps its state in `$XDG_RUNTIME_DIR/screen-lab/<id>/`:

- `state.json`: the lab's kind, its app's pid and start time, owner, output, workspace,
  window, grid, browser port, the keeper and any recording;
- `feed`: the FIFO, `size`, `go` (the relay's signal to start the command) and `osc52.log`;
- `casts/`: one file per ScreenCast session still open;
- `rec/`: a recording's frames;
- `terminal.log` or `browser.log`, `relay.log`, `rec.log`, and a browser lab's `keeper.log`
  and `filechooser.log`.

A browser lab's profile and downloads are in `$XDG_CACHE_HOME/niri-screen-lab/<id>/`.

The lab records each process it starts (Ghostty or Chromium, the recorder or poller, the
keeper) by pid and start time. Once one exits, the kernel may give its pid to another
process, even one of the user's own windows, so a command treats a process as the lab's only
while both match: it never drives or signals anything else.

A lab's owner is the session's `$CLAUDE_PID`, the `claude` process. While that process is
alive, every command on the lab from another session is refused, `stop` included. Once it
has exited, any session may drive or stop the lab.

**Stop and the sweep.** `stop --lab ID` ends the lab's processes, stops its cast sessions,
drops its workspace's name (niri then removes the empty workspace), and deletes its state
and profile. `list`, `start` and `browse` do the same for every lab whose app has exited,
whichever session started it: a dead lab has nothing left to protect.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `start` refused: no window rule | two or more outputs and no rule for the chosen one; relay the block preflight prints |
| `start` aborted and closed the lab | the window didn't end up unfocused on its own workspace; the message says which step failed |
| refused: `belongs to another Claude session` | another session is using that lab; open your own. Never stop it |
| `--lab` is required | every command on a lab needs the id `start` or `browse` printed |
| `no lab ID is running` right after start | the command exited; read the lab's `relay.log` and `terminal.log` |
| `shot` is slow on a terminal lab | a hidden window draws about once a second; that is expected |
| `cell` refuses: resized | the window changed size; restart the lab |
| keys do nothing | the app is in kitty keyboard mode and wants CSI-u; send them with `keys` |
| browser input refused: the window has focus | a windowed lab's window has focus; tell the user, or use a headless lab |
| a page's file upload does nothing | the lab held the chooser back (`filechooser.log`); load the content with `js` instead |
