declare module 'claude-code' {
  interface PluginState {
    // Whether mods should draw Nerd Font glyphs: the user's setting, or else whether an installed font's family
    // has "Nerd Font" in its name. Undefined until the session's check has run.
    'nerd-font': { enabled: boolean }
  }
}
