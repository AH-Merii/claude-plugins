---
name: screen-lab
description: Visually test terminal apps in a real Ghostty window on the user's spare monitor (niri), without stealing focus or touching the clipboard. Type keys, send mouse hovers and clicks, take screenshots, and record GIFs. Use it whenever you need to see what a TUI or CLI actually renders. Typical asks are "screenshot a terminal app", "test a Claude Code mod visually", "check how it looks in Ghostty", "record a GIF of the TUI", "hover/click test", and "images in the terminal" (kitty graphics). Use it too when verifying a UI change yourself before handing it back. Prefer it to tmux capture-pane, wtype, ydotool and niri screenshots, which all disturb the user or change the app.
---

# screen-lab

A real Ghostty window on a monitor the user is not working on. You drive it with `lab.py`,
which sits next to this file (call it by its path, e.g. `<skill-dir>/lab.py`). The window
opens unfocused, input goes through a pty relay instead of the keyboard, captures use grim
and wf-recorder, and the app inside gets no display access, so the user's focus and
clipboard stay as they were.

## Workflow

1. `lab.py preflight`. Every line must say `ok`. On a `FAIL`, stop and relay its fix to
   the user (it says what to ask, e.g. `sudo pacman -S grim`). Never work around a check.
2. Tell the user that the lab is about to open on the spare screen, and ask them to keep the
   pointer off it. Focus follows the mouse, so a pointer on the lab sends their typing there.
3. `lab.py start --cwd DIR -- CMD [ARGS...]`. It refuses if anything is off, and if the
   window lands anywhere but the spare output it closes it and aborts. Then report
   that to the user.
4. Drive and look, as often as needed:
   - `lab.py keys 'text\r'` for raw bytes, printf-style (`\e`, `\r`, `\x15`).
     `lab.py key enter esc ctrl-u up` for named keys.
   - `lab.py shot FILE.png --crop`, then view it with Read. Leave out `--crop` to get the
     whole spare output.
   - `lab.py cell X Y --crop` turns a pixel in a `--crop` shot into `COL ROW`. Use it with
     `lab.py hover COL ROW`, `lab.py click COL ROW` and `lab.py scroll down COL ROW`.
   - `lab.py gif FILE.gif SECONDS --crop &`, then drive the app, then `wait`. There is also
     `rec-start` / `rec-stop FILE.gif`.
5. `lab.py stop` when done, or before starting another command. It kills Ghostty, so no
   close dialog is left behind.

## Rules

- Never use `niri msg action screenshot*`, which always overwrites the clipboard. Use only
  `shot`, `gif` and grim.
- Never use wtype, ydotool or any real keyboard or mouse injection: they type into the
  user's focused window. Never put tmux inside the lab either: it changes the app (Claude
  Code turns images off under tmux, and keys are encoded differently).
- A screenshot covers the whole spare output, so `shot` and `gif` refuse unless the lab
  window is alone on that output's visible workspace. If they refuse, don't capture
  another way. Tell the user what is in the way.
- For a lab `claude`, use `--model haiku`. For repeatable content, use
  `--resume <test-session-id> --fork-session` on a session made for testing. Never resume
  the session you are running in. Start it with `--cwd` set to the project the session
  belongs to.
- If anything opens on the user's main screen, stop the lab at once and tell them.

Read [reference.md](reference.md) for prerequisites and why each rule exists. It also
covers mouse coordinates, OSC 52 clipboard logging, images, and troubleshooting.
