# niri-screen-lab

A skill that lets an agent look at a terminal app or a web page the way a person would. It
opens the app in a real Ghostty window, or the page in a real Chromium window on a throwaway
profile, on your spare monitor. It types into it, sends mouse hovers and clicks, and takes
screenshots and GIFs. Your focused window, keyboard and clipboard are never touched: a
terminal gets its input through a pty, and a browser through Chromium's DevTools protocol.

The agent picks it up on its own whenever it needs to see what a TUI, CLI or web page
renders, for example "screenshot this terminal app", "test the mod visually", "record a GIF
of the TUI", "hover/click test", "check the images in the terminal" or "preview this page".
It also uses it to check its own UI changes before handing them back.

As a skill, the rules come along every time: no `wtype` or `ydotool`, no
`niri msg action screenshot` (it writes the clipboard), no tmux in between, captures only
when the lab window is alone on the spare screen, and a stop the moment anything opens on
your main screen. A browser lab also refuses input while its window has focus, holds file
choosers back, and never uses your profile or keyring.

## Prerequisites

- niri, with two or more outputs. The spare one is `SCREEN_LAB_OUTPUT`, else an unfocused
  laptop panel (`eDP-*`), else the only unfocused output.
- Ghostty, grim, wf-recorder and ffmpeg on `PATH`, and python3 with PyGObject. Chromium too,
  for the browser lab.
- A niri window rule that opens the lab on the spare output, unfocused. Preflight prints the
  exact block for your setup, for example:

  ```kdl
  window-rule {
      match app-id=r#"^dev\.claude\.lab$"#
      open-on-output "eDP-1"
      open-focused false
  }
  ```

The agent runs `lab.py preflight` first. It checks all of this and tells you what to install
or add when something is missing.

## Install

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install niri-screen-lab@ah-merii
```

See [reference.md](skills/niri-screen-lab/reference.md) for the details behind each rule.

## Tests

```sh
python3 -m unittest discover -s plugins/niri-screen-lab/tests
```

They need only Python: a renamed `sleep` stands in for the lab's Ghostty or Chromium, and a
local socket for Chromium's DevTools. The opt-in run on the real desktop, with
`SCREEN_LAB_LIVE=1`, starts two labs at once, then drives a page in a browser lab. It needs
everything `preflight --browser` checks, and no lab running.
