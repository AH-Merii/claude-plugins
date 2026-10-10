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
    "branch": "`but branch new <name>` to create, `but branch delete <branch>` to delete, "
              "`but reword <branch> -m <new-name>` to rename, `but move` to restack",
    "clean": "`but discard <id>` on the untracked files (not `but clean`, which removes empty branches)",
}
# git subcommand -> why it's blocked and what to do, for writes `but` has no command for
UNSUPPORTED = {
    "tag": "`but` has no tag command, and a tag on a workspace commit goes stale once GitButler "
           "rewrites it (amend, squash, move, pull). Ask the user to tag released commits.",
    "rm": "`but` has no rm command, and GitButler doesn't use the index `git rm` stages into. "
          "Delete with plain `rm <path>`; `but commit` picks up the deletion.",
    "mv": "`but` has no mv command, and GitButler doesn't use the index `git mv` stages into. "
          "Rename with plain `mv <old> <new>`; `but commit` picks up the rename.",
    "update-ref": "`but` has no update-ref command, and moving refs behind GitButler's back "
                  "desyncs the workspace from its branch metadata. Change history with `but move`, "
                  "`but uncommit` or `but undo`.",
    "notes": "`but` has no notes command, and notes hang off commit hashes that GitButler rewrites "
             "(amend, squash, move, pull), so they'd be orphaned. Put the context in the commit "
             "message with `but reword`.",
}

BRANCH_WRITE = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                "-u", "--set-upstream-to", "--unset-upstream", "--edit-description", "-t", "--track",
                "--no-track", "--create-reflog", "--recurse-submodules"}
BRANCH_LIST = {"-l", "--list", "-a", "--all", "-r", "--remotes", "--show-current", "-v", "--verbose",
               "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
READ_ONLY_NOTES = {"list", "show", "get-ref"}
DRY_RUN = {"-n", "--dry-run"}
TAG_WRITE = {"-a", "--annotate", "-s", "--sign", "-u", "--local-user", "-f", "--force", "-d",
             "--delete", "-m", "--message", "-F", "--file", "-e", "--edit", "--trailer",
             "--cleanup", "--create-reflog"}
TAG_LIST = {"-l", "--list", "-n", "--contains", "--no-contains", "--merged", "--no-merged",
            "--points-at", "-v", "--verify"}

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


def parse_opts(args, takes_value=""):
    """Split a subcommand's args into (flags, operands).

    Short flags are split (`-dr` -> `-d`, `-r`) and `--opt=value` counts as `--opt`.
    Options named in `takes_value` (space-separated) skip their value.
    """
    takes_value = set(takes_value.split())
    flags, operands = set(), []
    args = iter(args)
    for arg in args:
        if arg == "--":
            operands.extend(args)
        elif arg.startswith("--"):
            name = arg.split("=", 1)[0]
            flags.add(name)
            if name in takes_value and "=" not in arg:
                next(args, None)
        elif arg.startswith("-") and len(arg) > 1:
            for j, ch in enumerate(arg[1:], 2):
                flags.add("-" + ch)
                if "-" + ch in takes_value:
                    if j == len(arg):
                        next(args, None)
                    break
        else:
            operands.append(arg)
    return flags, operands


def branch_read_only(args):
    flags, operands = parse_opts(args, "-u --set-upstream-to --sort --format --points-at")
    return not flags & BRANCH_WRITE and (bool(flags & BRANCH_LIST) or not operands)


def tag_read_only(args):
    flags, operands = parse_opts(args, "-u --local-user -m --message -F --file --trailer --cleanup "
                                       "--sort --format --points-at")
    return not flags & TAG_WRITE and (bool(flags & TAG_LIST) or not operands)


def dry_run(args, takes_value=""):
    return bool(parse_opts(args, takes_value)[0] & DRY_RUN)


def notes_read_only(args):
    operands = parse_opts(args, "--ref")[1]
    return not operands or operands[0] in READ_ONLY_NOTES


# git subcommand -> test for the read-only forms of a blocked command
READ_ONLY = {
    "stash": lambda args: bool(args) and args[0] in {"list", "show"},
    "branch": branch_read_only,
    "tag": tag_read_only,
    "rm": dry_run,
    "mv": dry_run,
    "notes": notes_read_only,
    "clean": lambda args: dry_run(args, "-e --exclude"),
}


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
    """Return (subcommand, advice) for the first blocked git command, else None."""
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
        if sub not in BLOCKED and sub not in UNSUPPORTED:
            continue
        if sub in READ_ONLY and READ_ONLY[sub](rest):
            continue
        if in_workspace(repo, cache):
            return sub, f"Use {BLOCKED[sub]} instead." if sub in BLOCKED else UNSUPPORTED[sub]
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
        sub, advice = hit
        reason = (
            f"`git {sub}` is blocked in this GitButler workspace. {advice} "
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
