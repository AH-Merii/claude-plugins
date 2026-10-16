# nerd-font

A Claude Code mod that other mods depend on to know whether they can draw Nerd Font icons. It works out the answer once a session, so every mod on screen draws the same way: `attention`'s magnifying glass and `copy-code`'s copy label either both use the icon or both fall back to plain characters.

## How it decides

The mod API can't tell which font the terminal draws with, so the mod asks fontconfig instead. If any installed family that `fc-list : family` lists has "Nerd Font" in its name, the answer is yes. If there's no such family, or no `fc-list`, the answer is no.

A Nerd Font being installed doesn't mean your terminal uses it. If the guess is wrong, use the setting.

## Setting

In `/config`, the **Nerd Font glyphs** row picks one of:

| Value | Icons are drawn |
| --- | --- |
| `auto` (default) | when `fc-list` finds a Nerd Font |
| `on` | always |
| `off` | never |

A change there reloads the mod with the new value, and the mods that read the answer while drawing redraw. The value is kept in `settings.json` under `pluginConfigs`.

## For mod authors

List `nerd-font` under `dependencies` in your `plugin.json`:

```json
{ "dependencies": ["nerd-font"] }
```

Read the answer from `$.state` while drawing. Your drawing then redraws when the answer arrives or changes:

```tsx
const nerdFont = { plugin: 'nerd-font', key: 'enabled' } as const

on('ui.render', { component: 'AbovePrompt', surface: 'terminal' }, async ($, e) => {
  const { value: hasNerdFont } = await $.state.get(nerdFont)
  const { Text } = $.ui.resolve(e)
  return <Text>{hasNerdFont ? '\u{F0349}' : '🔍'}</Text>
})
```

The value is `undefined` until the session's check has run, so treat anything but `true` as no. Claude Code lays this mod's contract into your mod's `.claude-plugin/types/nerd-font/index.d.ts`, so the key and its type are checked.

## Install

```text
/plugin install nerd-font --marketplace AH-Merii/claude-plugins
```
