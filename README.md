# claude-plugins

My Claude Code skills and mods, as one plugin marketplace (`ah-merii`).

| Name | Type | Use it when… |
|------|------|--------------|
| [screen-lab](plugins/screen-lab) | skill | an agent needs to see what a terminal app really renders: screenshots, GIFs, hover and click tests in Ghostty on a spare niri screen |
| [gitbutler-guard](plugins/gitbutler-guard) | hooks | an agent works in a GitButler workspace: blocks git write commands in favour of `but`, and keeps the GitButler skill in step with your `but` CLI |

## Install

From the shell:

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install screen-lab@ah-merii
```

Or inside a session:

```
/plugin marketplace add AH-Merii/claude-plugins
/plugin install screen-lab@ah-merii
```

Then restart the session, or run `/reload-plugins`.

## Update

```sh
claude plugin marketplace update ah-merii && claude plugin update screen-lab@ah-merii
```

Restart the session afterwards. To update automatically, turn on auto-update for `ah-merii`
under `/plugin` → Marketplaces.

## Requirements

Claude Code with the `claude plugin` command, tested on 2.1.289. Mods will need 2.1.287 or
newer. Each plugin's README lists its own prerequisites.

## Layout

Every plugin is one folder under `plugins/`, whatever it contains. Its type is just which
component folders it has, so a plugin that gains a skill or a hook never moves:

```
plugins/<name>/
├── .claude-plugin/plugin.json   # name, version, author, license, …
├── skills/<skill>/SKILL.md      # a skill, plus its references and scripts
├── hooks/hooks.json             # every hook the plugin registers
├── hooks/*.py, *.sh             # command-hook scripts
├── hooks/register.tsx           # a mod: live-UI function hooks, shipped as-is, no build step
├── tests/                       # claude plugin test plugins/<name> for mods
└── README.md                    # what it does, prerequisites, caveats, a GIF for UI
```

Add each plugin to `.claude-plugin/marketplace.json` with `"source": "./plugins/<name>"`
and tags naming its components. The generated `.claude-plugin/types/` is gitignored.

Check a change with `claude plugin validate --strict .` and
`claude plugin validate --strict plugins/<name>`.

## License

[MIT](LICENSE), copyright 2026 AH-Merii (AbdulHamid Merii).
