#!/usr/bin/env python3
"""PreToolUse(Bash) hook: in a GitButler workspace, deny git write commands and name the `but` one.

Only repos whose HEAD is `gitbutler/workspace` are guarded, so plain git repos and linked
worktrees (where `but commit` is unsupported) keep working. Read-only git is never blocked.
Any parsing or git failure lets the command through.
"""
import json
import os
import shlex
import subprocess
import sys

WORKSPACE_BRANCH = "gitbutler/workspace"

# git subcommand -> what to run instead
BLOCKED = {
    "add": '`but commit -b <branch> -m "<msg>" <ids>` (no staging step; take IDs from `but diff`)',
    "commit": '`but commit -b <branch> -m "<msg>" <ids>`, or `but amend -t <commit> <ids>`',
    "push": "`but push <branch>`, or `but pr new <branch>` to push and open a PR",
    "pull": "`but pull`",
    "checkout": '`but commit -b <new-branch> -m "<msg>" <ids>` to start a branch, `but discard <id>` to drop changes',
    "switch": '`but commit -b <new-branch> -m "<msg>" <ids>` to start a branch',
    "restore": "`but discard <id>`",
    "reset": "`but uncommit <commit>`, `but discard <id>`, or `but undo`",
    "merge": "`but pull` to update from the target branch",
    "rebase": "`but pull` (onto the target), `but move` / `but squash` / `but reword` (history edits)",
    "stash": '`but commit -b <branch> -m "wip" <ids>`, then `but uncommit` it later',
    "cherry-pick": "`but pick`",
}
READ_ONLY_STASH = {"list", "show"}

SEPARATORS = {";", "&", "&&", "|", "||", "|&", "(", ")", "\n"}
WRAPPERS = {"sudo", "env", "command", "builtin", "exec", "nohup", "time", "nice"}
# git global options that take a separate value
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}


def tokenize(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    return list(lex)


def segments(tokens):
    seg = []
    for tok in tokens:
        if tok in SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def strip_prefix(seg):
    """Drop `VAR=value` assignments and wrappers like `sudo` or `env` before the program."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if tok in WRAPPERS or ("=" in tok and not tok.startswith("-") and tok.split("=", 1)[0].isidentifier()):
            i += 1
        else:
            break
    return seg[i:]


def parse_git(args, cwd):
    """Return (subcommand, rest, repo_dir) for the args after `git`."""
    repo = cwd
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in GIT_OPTS_WITH_VALUE:
            if arg == "-C" and i + 1 < len(args):
                repo = os.path.join(repo, os.path.expanduser(args[i + 1]))
            i += 2
        elif arg.startswith("-"):
            i += 1
        else:
            return arg, args[i + 1 :], repo
    return None, [], repo


def in_workspace(path, cache):
    if path not in cache:
        try:
            out = subprocess.run(
                ["git", "-C", path, "symbolic-ref", "--short", "-q", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            cache[path] = out.stdout.strip() == WORKSPACE_BRANCH
        except (OSError, subprocess.SubprocessError):
            cache[path] = False
    return cache[path]


def find_violation(command, cwd):
    """Return (subcommand, replacement) for the first blocked git command, else None."""
    cache = {}
    for seg in segments(tokenize(command)):
        seg = strip_prefix(seg)
        if not seg:
            continue
        if seg[0] == "cd":
            target = seg[1] if len(seg) > 1 else "~"
            cwd = os.path.join(cwd, os.path.expanduser(target))
            continue
        if os.path.basename(seg[0]) != "git":
            continue
        sub, rest, repo = parse_git(seg[1:], cwd)
        if sub not in BLOCKED:
            continue
        if sub == "stash" and rest and rest[0] in READ_ONLY_STASH:
            continue
        if in_workspace(repo, cache):
            return sub, BLOCKED[sub]
    return None


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command") or ""
        cwd = data.get("cwd") or os.getcwd()
        hit = find_violation(command, cwd)
    except Exception:
        return 0
    if hit:
        sub, replacement = hit
        reason = (
            f"`git {sub}` is blocked in this GitButler workspace. Use {replacement} instead. "
            "Read-only git (log, show, blame, diff, status) is still allowed; "
            "see the GitButler `but` skill for syntax."
        )
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
