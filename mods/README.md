# mods

One plugin per mod: live UI and hooks inside Claude Code. None yet.

```
mods/<name>/
├── .claude-plugin/plugin.json   # name, version, author, license, …
├── hooks/hooks.json
├── hooks/register.tsx           # shipped as-is, no build step
├── tests/*.test.ts              # claude plugin test mods/<name>
└── README.md                    # terminal-only caveats, a GIF
```

Add each one to `.claude-plugin/marketplace.json` with `"source": "./mods/<name>"`. The
generated `.claude-plugin/types/` is gitignored.
