---
name: niri-screen-lab
description: Visually test terminal apps in a real Ghostty window, or web pages in a real Chromium window, on the user's spare monitor (niri), without stealing focus or touching the clipboard. Type keys, send mouse hovers and clicks, take screenshots, and record GIFs. Use it whenever you need to see what a TUI, CLI or web page actually renders. Typical asks are "screenshot a terminal app", "test a Claude Code mod visually", "check how it looks in Ghostty", "record a GIF of the TUI", "hover/click test", "images in the terminal" (kitty graphics), "open this page and screenshot it", "preview this diagram/HTML in a browser", and "click through the web UI". Use it too when verifying a UI change yourself before handing it back. Prefer it to tmux capture-pane, wtype, ydotool, niri screenshots and launching a browser yourself, which all disturb the user or change the app.
---

# niri-screen-lab

A real window on a monitor the user is not working on: Ghostty running a command (a
terminal lab), or Chromium on a throwaway profile (a browser lab). You drive it with
`lab.py`, which sits next to this file (call it by its path, e.g. `<skill-dir>/lab.py`).
The window opens unfocused and captures use grim and wf-recorder. Input never goes through
the compositor: a terminal lab's goes through a pty relay, a browser lab's through Chromium's
DevTools protocol. So the user's focus and clipboard stay as they were.

## Workflow

1. `lab.py preflight` (add `--browser` for a browser lab). Every line must say `ok`. On a
   `FAIL`, stop and relay its fix to the user (it says what to ask, e.g.
   `sudo pacman -S grim`). Never work around a check.
2. Tell the user that the lab is about to open on the spare screen, and ask them to keep the
   pointer off it. Focus follows the mouse, so a pointer on the lab sends their typing there.
3. Open one lab:
   - `lab.py start --cwd DIR -- CMD [ARGS...]` for a terminal app;
   - `lab.py browse URL` for a web page (`file://`, `http(s)://` or `data:`).

   Either refuses if anything is off, and if the window lands anywhere but the spare output it
   closes it and aborts. Then report that to the user.
4. Drive and look, as often as needed:
   - `lab.py keys 'text\r'` for text, printf-style (`\e`, `\r`, `\x15`).
     `lab.py key enter esc ctrl-u up` for named keys; a browser lab also takes
     `ctrl-shift-p`-style combinations.
   - `lab.py shot FILE.png --crop`, then view it with Read. `--crop` is the terminal grid or
     the page's viewport. Leave it out to get the whole spare output.
   - `lab.py cell X Y --crop` turns a pixel in a `--crop` shot into what the mouse commands
     take: `COL ROW` in a terminal lab, the page's CSS `X Y` in a browser lab. Use it with
     `lab.py hover`, `lab.py click` and `lab.py scroll down`.
   - Browser lab only: `lab.py open URL` to go elsewhere, and `lab.py js 'EXPR'` to evaluate
     JavaScript in the page (its JSON value is printed). Use `js` to find an element's
     position (`getBoundingClientRect()`), read state, or load content into the page.
   - `lab.py gif FILE.gif SECONDS --crop &`, then drive the app, then `wait`. There is also
     `rec-start` / `rec-stop FILE.gif`. A GIF needs something to move while it records.
5. `lab.py stop` when done, or before starting another lab. It ends Ghostty or Chromium, so
   no close dialog is left behind, and deletes the browser profile.

## Rules

- Never use `niri msg action screenshot*`, which always overwrites the clipboard. Use only
  `shot`, `gif` and grim.
- Never use wtype, ydotool or any real keyboard or mouse injection: they type into the
  user's focused window. Never put tmux inside the lab either: it changes the app (Claude
  Code turns images off under tmux, and keys are encoded differently).
- Never open a browser yourself to show or test a page: use `browse`. A browser you launch
  opens focused on the user's screen.
- A screenshot covers the whole spare output, so `shot` and `gif` refuse unless the lab
  window is alone on that output's visible workspace. If they refuse, don't capture
  another way. Tell the user what is in the way.
- A browser lab refuses input while its window has focus: only the focused window can set
  the clipboard. Ask the user to move the pointer off the spare screen, then retry.
- In a browser lab, don't try to get past a file chooser: the lab holds it back and logs it
  (`filechooser.log`). Load content with `js` or a URL instead. Never sign in to anything in
  a lab browser.
- For a lab `claude`, use `--model haiku`. For repeatable content, use
  `--resume <test-session-id> --fork-session` on a session made for testing. Never resume
  the session you are running in. Start it with `--cwd` set to the project the session
  belongs to.
- A lab belongs to the Claude session that started it. While that session is alive, every
  command from another session is refused with "belongs to another Claude session". Then
  don't stop it, kill its window or delete its state: another agent is using it. Try again
  later, or tell the user.
- If anything opens on the user's main screen, stop the lab at once and tell them.

Read [reference.md](reference.md) for prerequisites and why each rule exists. It also
covers mouse coordinates, OSC 52 clipboard logging, images, the browser lab, and
troubleshooting.
