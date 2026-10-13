# niri-screen-lab

A skill that lets an agent look at a terminal app or a web page the way a person would. It
opens the app in a real Ghostty window, or the page in Chromium on a throwaway profile,
headless unless the agent asks for a window. Each lab window lives on a niri workspace of
its own that you never see. The agent types into it, sends mouse hovers and clicks, and
takes screenshots and GIFs. Your focused window, keyboard and clipboard are never touched: a
terminal gets its input through a pty and is captured through niri's ScreenCast service, and
a browser goes through Chromium's DevTools protocol. Several labs run at once, from one
agent or many.

The agent picks it up on its own whenever it needs to see what a TUI, CLI or web page
renders, for example "screenshot this terminal app", "test the mod visually", "record a GIF
of the TUI", "hover/click test", "check the images in the terminal" or "preview this page".
It also uses it to check its own UI changes before handing them back.

As a skill, the rules come along every time: no `wtype` or `ydotool`, no
`niri msg action screenshot` (it writes the clipboard), no tmux in between, every command
names its lab, and a stop the moment anything opens on your visible screens. A windowed
browser lab also refuses input while its window has focus; every browser lab holds file
choosers back and never uses your profile or keyring.

## Prerequisites

- niri. With one screen, lab windows go to hidden workspaces on it, and you are told when a
  new one holds focus for about 50 ms. With two or more, they go to a spare one:
  `SCREEN_LAB_OUTPUT`, else an unfocused laptop panel (`eDP-*`), else the only unfocused
  output.
- Ghostty, gdbus, GStreamer (`gst-launch-1.0` with the PipeWire and VA plugins) and ffmpeg
  on `PATH`, and python3 with PyGObject. Chromium too, for the browser lab.
- With two or more screens, a niri window rule that opens lab windows on the spare output,
  unfocused. Preflight prints the exact block for your setup, for example:

  ```kdl
  window-rule {
      match app-id=r#"^dev\.claude\.lab$"#
      open-on-output "eDP-1"
      open-focused false
  }
  ```

The agent runs `lab.py preflight` first. It checks all of this, tells you what to install
or add when something is missing, and shows the memory free against what labs typically cost.

## Install

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install niri-screen-lab@ah-merii
```

See [reference.md](skills/niri-screen-lab/reference.md) for the details behind each rule.

## Tests

```sh
python3 -m unittest discover -s plugins/niri-screen-lab/tests
```

They need only Python. `lab.py` runs against fakes of its outside boundaries: niri's IPC
socket and its ScreenCast sessions, `gdbus`, `gst-launch-1.0`, Ghostty, Chromium's DevTools
and ffmpeg. After every test they check that no focus or screenshot action reached niri and
that no DevTools call raised a window. The opt-in run on the real desktop, with
`SCREEN_LAB_LIVE=1`, runs terminal and browser labs side by side on hidden workspaces. It
needs everything `preflight --browser` checks.
