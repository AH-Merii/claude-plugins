# gitbutler-guard

Hooks that keep an agent on GitButler's `but` CLI. Two jobs:

- **Block git writes in GitButler workspaces.** A `PreToolUse` hook on Bash denies `git add`,
  `commit`, `push`, `pull`, `checkout`, `switch`, `restore`, `reset`, `merge`, `rebase`,
  `stash`, `cherry-pick`, `rm`, `mv`, `clean` and `update-ref`, plus the writing forms of
  `branch`, `tag`, `notes` and `config`. It tells the agent which `but` command to run
  instead, or why there isn't one. Read-only git (`log`, `show`, `blame`, `diff`, `status`,
  `stash list`, listing branches and tags, `notes show`, `config --get`, dry runs) still works.
- **Keep the GitButler skill current.** At session start, a hook compares the skill in your
  Claude config's `skills/gitbutler/` with `but --version`. If it's missing or a different
  version, it reinstalls it with `but skill install --path`.

The skill isn't bundled. `but` generates it and stamps it with its own version, so the right
copy is always the one that matches the CLI you have installed.

## What counts as a GitButler workspace

A repo whose `HEAD` is `gitbutler/workspace`. Other repos, and linked worktrees (where
`but commit` is unsupported), aren't guarded. The hook follows `cd <dir>` and
`git -C <dir>` to find the repo, and checks every command in a chain (`&&`, `;`, `|`,
newlines, subshells).

It's a guardrail, not a sandbox: `bash -c "git commit"` or a heredoc that runs git gets
past it. If anything fails to parse, the command goes through.

## Requirements

- `python3` on `PATH`
- [GitButler CLI](https://docs.gitbutler.com/cli-overview) (`but`) for the skill sync; the
  guard works without it

The skill goes to `$CLAUDE_CONFIG_DIR/skills/gitbutler`, or `~/.claude/skills/gitbutler`
when `CLAUDE_CONFIG_DIR` isn't set.

## Tests

```sh
python3 -m unittest discover -s plugins/gitbutler-guard/tests
```
