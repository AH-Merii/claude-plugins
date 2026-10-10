#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny PR and issue review/comment writes and name the pr-threads command.

Covers `gh pr comment`, `gh pr review`, `gh issue comment`, `gh api` writes to the review and
comment REST endpoints, and the review and comment GraphQL mutations. Reads are never blocked.
A command shlex can't split is checked roughly, line by line: any `gh` in it counts.
Known gap: a GraphQL query read from a file (`-F query=@file`) can't be classified.
"""
import json
import os
import re
import shlex
import sys

# pr-threads verb -> what it does, for the deny message
VERBS = {
    "comment": "an inline comment on a diff line",
    "reply": "a reply in a review thread",
    "resolve": "resolving review threads",
    "submit": "a review with a verdict, posted as the bot",
    "post": "a general comment on a PR or issue conversation",
}
# `gh <group> <command>` -> pr-threads verb
GH_COMMANDS = {("pr", "comment"): "post", ("pr", "review"): "submit", ("issue", "comment"): "post"}
# GraphQL mutation -> pr-threads verb, or None where pr-threads has no equivalent
MUTATIONS = {
    "addComment": "post",
    "addPullRequestReviewThread": "comment",
    "addPullRequestReviewComment": "comment",
    "addPullRequestReviewThreadReply": "reply",
    "resolveReviewThread": "resolve",
    "addPullRequestReview": "submit",
    "submitPullRequestReview": "submit",
    "unresolveReviewThread": None,
    "updateIssueComment": None,
    "deleteIssueComment": None,
    "updatePullRequestReview": None,
    "updatePullRequestReviewComment": None,
    "deletePullRequestReviewComment": None,
    "dismissPullRequestReview": None,
    "deletePullRequestReview": None,
    "minimizeComment": None,
    "unminimizeComment": None,
}
# REST: repos/<o>/<r>/{pulls,issues}/[<n>/]{comments,reviews}[/<id>[/<action>]]
ENDPOINT = re.compile(r"/?repos/[^/]+/[^/]+/(pulls|issues)/(?:\d+/)?(comments|reviews)"
                      r"(?:/([^/?]+)(?:/(replies|events|dismissals))?)?/?(?:\?.*)?")
# (kind, collection, has id, action) -> pr-threads verb; other writes there have none
ENDPOINT_VERBS = {
    ("pulls", "comments", False, None): "comment",
    ("pulls", "comments", True, "replies"): "reply",
    ("pulls", "reviews", False, None): "submit",
    ("pulls", "reviews", True, "events"): "submit",
    ("issues", "comments", False, None): "post",
}
READ_METHODS = {"GET", "HEAD"}

API_OPTS_WITH_VALUE = {"-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
                       "--input", "-q", "--jq", "-t", "--template", "--cache", "-p", "--preview",
                       "--hostname"}
API_BODY_OPTS = {"-f", "--raw-field", "-F", "--field", "--input"}

SEPARATORS = {";", "&", "&&", "|", "||", "|&", "(", ")", "`", "\n"}
WRAPPERS = {"sudo", "env", "command", "builtin", "exec", "nohup", "time", "nice", "xargs"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}


def tokenize(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()`\n")
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


def parse_api(args):
    """Return (method, endpoint, args text) for the args after `gh api`."""
    method, endpoint, body = None, None, False
    it = iter(args)
    for arg in it:
        name, value = arg, None
        if arg.startswith("--") and "=" in arg:
            name, value = arg.split("=", 1)
        elif not arg.startswith("--") and arg[:2] in API_OPTS_WITH_VALUE and len(arg) > 2:
            name, value = arg[:2], arg[2:]  # -XPOST, -fbody=x
        if name in API_OPTS_WITH_VALUE:
            value = next(it, "") if value is None else value
            if name in ("-X", "--method"):
                method = value.upper()
            body = body or name in API_BODY_OPTS
        elif not arg.startswith("-") and endpoint is None:
            endpoint = arg
    return method or ("POST" if body else "GET"), endpoint or "", " ".join(args)


def check_api(args):
    """Return (what, verb) for a `gh api` review or comment write, else None."""
    method, endpoint, text = parse_api(args)
    if endpoint.lstrip("/") == "graphql":
        for word in re.findall(r"\w+", text):
            if word in MUTATIONS:
                return f"The GraphQL mutation `{word}`", MUTATIONS[word]
        return None
    m = ENDPOINT.fullmatch(endpoint)
    if not m or method in READ_METHODS:
        return None
    kind, collection, ident, action = m.groups()
    verb = ENDPOINT_VERBS.get((kind, collection, bool(ident), action))
    return f"`gh api -X {method} {endpoint}`", verb


def check_gh(args):
    """Return (what, verb) for the args after `gh` when they write a review or comment."""
    if len(args) >= 2 and (args[0], args[1]) in GH_COMMANDS:
        return f"`gh {args[0]} {args[1]}`", GH_COMMANDS[args[0], args[1]]
    if args and args[0] == "api":
        return check_api(args[1:])
    return None


def check_segment(seg):
    seg = strip_prefix(seg)
    if not seg:
        return None
    prog, args = os.path.basename(seg[0]), seg[1:]
    if prog == "gh":
        return check_gh(args)
    if prog == "eval":
        return check(" ".join(args))
    if prog in SHELLS:
        for i, arg in enumerate(args[:-1]):
            if arg.startswith("-") and not arg.startswith("--") and "c" in arg:
                return check(args[i + 1])
    return None


def check_rough(command):
    """For text shlex can't split: check from every `gh` on each line, ignoring quotes."""
    for line in command.splitlines():
        words = re.findall(r"[^\s;&|()<>'\"`]+", line)
        for i, word in enumerate(words):
            if os.path.basename(word) == "gh" and (hit := check_gh(words[i + 1 :])):
                return hit
    return None


def check(command):
    try:
        tokens = tokenize(command)
    except ValueError:
        return check_rough(command)
    for seg in segments(tokens):
        if hit := check_segment(seg):
            return hit
    return None


def find_violation(command):
    """Return the deny reason for the first PR review or comment write, else None."""
    hit = check(command)
    if not hit:
        return None
    what, verb = hit
    if verb is None:
        advice = ("pr-threads has no command for editing, dismissing, unresolving or deleting "
                  "existing reviews and comments; ask the user to do it on GitHub.")
    else:
        advice = f"Use `pr-threads {verb}` ({VERBS[verb]}) instead; see the pr-threads skill for syntax."
    return (f"{what} is blocked: PR and issue review conversations go through pr-threads. {advice} "
            "Reading is still allowed (`gh pr view --comments`, `gh api` GETs, `pr-threads threads`).")


def main():
    try:
        data = json.load(sys.stdin)
        reason = find_violation(data.get("tool_input", {}).get("command") or "")
    except Exception:
        return 0
    if reason:
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
