# claude-plugins

My Claude Code skills and mods, as one plugin marketplace (`ah-merii`).

| Name | Type | Use it when… |
|------|------|--------------|
| [screen-lab](plugins/screen-lab) | skill | an agent needs to see what a terminal app really renders: screenshots, GIFs, hover and click tests in Ghostty on a spare niri screen |

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

- `skills/<name>/`: one plugin per skill. The skill itself sits in its `skills/<name>/`.
- `mods/<name>/`: one plugin per mod. See [mods/README.md](mods/README.md).
- `.claude-plugin/marketplace.json`: the catalog that lists them all.

Check a change with `claude plugin validate --strict .` and
`claude plugin validate --strict <plugin folder>`.

## License

[MIT](LICENSE), copyright 2026 AH-Merii (AbdulHamid Merii).
