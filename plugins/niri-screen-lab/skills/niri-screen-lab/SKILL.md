---
name: niri-screen-lab
description: Visually test terminal apps in a real Ghostty window, or web pages in Chromium, on a hidden niri workspace, without stealing focus or touching the clipboard. Several labs can run at once. Type keys, send mouse hovers and clicks, take screenshots, and record GIFs. Use it whenever you need to see what a TUI, CLI or web page actually renders. Typical asks are "screenshot a terminal app", "test a Claude Code mod visually", "check how it looks in Ghostty", "record a GIF of the TUI", "hover/click test", "images in the terminal" (kitty graphics), "open this page and screenshot it", "preview this diagram/HTML in a browser", and "click through the web UI". Use it too when verifying a UI change yourself before handing it back. Prefer it to tmux capture-pane, wtype, ydotool, niri screenshots and launching a browser yourself, which all disturb the user or change the app.
---

# niri-screen-lab

A lab is Ghostty running a command (a terminal lab), or Chromium on a throwaway profile (a
browser lab). You drive it with `lab.py`, which sits next to this file (call it by its path,
e.g. `<skill-dir>/lab.py`). Each lab window lives on a niri workspace of its own,
`claude-lab-<id>`, which the user never sees. A browser lab is headless unless you ask for a
window. Input never goes through the compositor: a terminal lab's goes through a pty relay,
a browser lab's through Chromium's DevTools protocol. Captures come from niri's ScreenCast
service or DevTools, never from a screenshot of the screen. So the user's focus and clipboard
stay as they were, and several labs, yours or other agents', can run side by side.

## First, do you need a lab?

- For a terminal app, if its plain text output is enough, run the command and read it. Use a
  lab only to see what it renders: colours, layout, images, mouse behaviour.
- For a web page, use a headless browser lab (`browse URL`). Add `--window` only when you
  need the real Chromium window.

## Workflow

1. `lab.py preflight` (add `--browser` for a browser lab). Every line must say `ok`. On a
   `FAIL`, stop and relay its fix to the user (it says what to ask). Never work around a check.
   It also prints the memory available and what labs typically cost (see Memory below).
2. Open a lab. Each prints `lab <id>`; pass that id to every later command as `--lab <id>`.
   - `lab.py start --cwd DIR -- CMD [ARGS...]` for a terminal app;
   - `lab.py browse URL` for a web page (`file://`, `http(s)://` or `data:`), headless;
     `lab.py browse --window URL` for a real window.

   Either refuses if anything is off. If a window can't be placed on its hidden workspace,
   unfocused, it is closed and the command refuses. Report that to the user.
3. Drive and look, as often as needed. Every command below takes `--lab ID`:
   - `lab.py keys 'text\r' --lab ID` for text, printf-style (`\e`, `\r`, `\x15`).
     `lab.py key enter esc ctrl-u up --lab ID` for named keys; a browser lab also takes
     `ctrl-shift-p`-style combinations.
   - `lab.py shot FILE.png --lab ID`, then view it with Read. It is the whole lab window, or
     the page. `--crop` narrows a terminal shot to its grid.
   - `lab.py cell X Y --lab ID` turns a pixel in a shot (add `--crop` for a `--crop` shot) into
     what the mouse commands take: `COL ROW` in a terminal lab, the page's CSS `X Y` in a
     browser lab. Use it with `hover`, `click` and `scroll down`.
   - Browser lab only: `lab.py open URL --lab ID` to go elsewhere, and `lab.py js 'EXPR' --lab ID`
     to evaluate JavaScript in the page (its JSON value is printed). Use `js` to find an
     element's position (`getBoundingClientRect()`), read state, or load content.
   - `lab.py gif FILE.gif SECONDS --lab ID &`, then drive the app, then `wait`. There is also
     `rec-start` / `rec-stop FILE.gif`. A GIF needs something to move while it records.
4. `lab.py stop --lab ID` when done. It ends the lab's processes and cast sessions, gives its
   workspace back, and deletes its state and browser profile.

`lab.py list` shows every lab, from every session: id, kind, owner, output, workspace and
whether it is alive. `list`, `start` and `browse` also clear away labs whose app has exited.

## Hidden terminals draw about once a second

niri draws a window on a hidden workspace about once a second. So a terminal `shot` can take
up to about 2 s: it waits for a frame drawn after the shot began, so it always shows your
last input. A terminal GIF holds about 1 frame a second. Browser captures come from DevTools
instead, at about 10 frames a second.

## Memory

`preflight`, `start` and `browse` print `MemAvailable` and typical costs: about 80–110 MiB per
terminal lab, plus about 50 MiB per running recording, about 280–300 MiB per headless browser
lab and about 340–460 MiB per windowed one. Weigh that against your task before opening another lab. If memory is short,
wait, or stop a lab you no longer need. There is no hard limit: it is your call.

## Rules

- Never use `niri msg action screenshot*`, which always overwrites the clipboard, or any
  other screen capture. Use only `shot`, `gif` and `rec-start`/`rec-stop`.
- Never use wtype, ydotool or any real keyboard or mouse injection: they type into the
  user's focused window. Never put tmux inside the lab either: it changes the app (Claude
  Code turns images off under tmux, and keys are encoded differently).
- Never open a browser yourself to show or test a page: use `browse`. A browser you launch
  opens focused on the user's screen.
- Never focus or switch to a lab's workspace, and never ask the user to.
- Always pass `--lab` with the id your own `start` or `browse` printed. Never pick one from
  `list`: a sibling subagent shares your session, so its labs look like yours.
- With a single screen, `start` and `browse --window` print "Tell the user: the new lab window
  holds keyboard focus for about 50 ms…". Relay it to the user.
- A windowed browser lab refuses input while its window has focus: only the focused window
  can set the clipboard. Tell the user, then retry. A headless lab has no window to focus.
  A windowed lab closes popups, pages that open in a new window; use a headless lab to test them.
- In a browser lab, don't try to get past a file chooser: the lab holds it back and logs it
  (`filechooser.log`). Load content with `js` or a URL instead. Never sign in to anything in
  a lab browser.
- For a lab `claude`, use `--model haiku`. For repeatable content, use
  `--resume <test-session-id> --fork-session` on a session made for testing. Never resume
  the session you are running in. Start it with `--cwd` set to the project the session
  belongs to.
- A lab belongs to the Claude session that started it. While that session is alive, every
  command from another session is refused with "belongs to another Claude session". Then
  don't stop it, kill its window or delete its state: another agent is using it. Open your
  own lab instead.
- If anything opens on the user's visible screens, stop the lab at once and tell them.

Read [reference.md](reference.md) for prerequisites and why each rule exists. It also
covers placement, mouse coordinates, OSC 52 clipboard logging, images, the browser lab, and
troubleshooting.
