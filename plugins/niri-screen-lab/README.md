# niri-screen-lab

A skill that lets an agent look at a terminal app the way a person would. It opens the app
in a real Ghostty window on your spare monitor, types into it through a pty, sends mouse
hovers and clicks, and takes screenshots and GIFs. Your focused window, keyboard and
clipboard are never touched.

The agent picks it up on its own whenever it needs to see what a TUI or CLI renders, for
example "screenshot this terminal app", "test the mod visually", "record a GIF of the TUI",
"hover/click test" or "check the images in the terminal". It also uses it to check its own
UI changes before handing them back.

As a skill, the rules come along every time: no `wtype` or `ydotool`, no
`niri msg action screenshot` (it writes the clipboard), no tmux in between, captures only
when the lab window is alone on the spare screen, and a stop the moment anything opens on
your main screen.

## Prerequisites

- niri, with two or more outputs. The spare one is `SCREEN_LAB_OUTPUT`, else an unfocused
  laptop panel (`eDP-*`), else the only unfocused output.
- Ghostty, grim, wf-recorder and ffmpeg on `PATH`, and python3 with PyGObject.
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
