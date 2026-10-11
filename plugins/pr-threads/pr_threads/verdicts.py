"""The bot's verdicts on a thread: its verify, withdraw, dispute and reopen replies, told apart by a marker.

A verdict counts only when the bot wrote it: a marker pasted by anyone else is just text.
"""
import json
import os

from pr_threads import Refusal
from pr_threads.threads import nodes

# marker kind -> what the reply is
KINDS = {"verify": "verification", "withdraw": "withdrawal", "dispute": "dispute", "reopen": "reopening"}
# the bot's latest verdict -> why it keeps the thread from resolving, whatever came after it
BLOCKING = {"dispute": "is disputed: the bot's latest verdict on it is a dispute",
            "reopen": "was reopened: the bot's latest verdict on it is that the fix didn't work"}
MARKER = "<!-- pr-threads:%s -->"
# the latest comments are what count, so read from the end of each thread
FIELDS = "id isResolved comments(last: 100) { nodes { author { login } body } }"


def bot_slug():
    """The reviewer app's slug, from the app.json reviewer-setup.py saved, or None."""
    folder = os.environ.get("CLAUDE_REVIEWER_DIR") or os.path.expanduser("~/.config/claude-reviewer")
    try:
        with open(os.path.join(folder, "app.json")) as f:
            return json.load(f).get("slug")
    except (OSError, ValueError):
        return None


def body(kind, text):
    """What the bot posts for a verdict: the text, then the hidden marker."""
    return f"{text}\n\n{MARKER % kind}\n"


def login(comment):
    return (comment.get("author") or {}).get("login")


def kind(comment):
    return next((k for k in KINDS if MARKER % k in comment["body"]), None)


def bot_kinds(thread, bot):
    """The bot's verdicts on `thread`, oldest first. GraphQL shows the bot as its bare slug."""
    comments = (thread.get("comments") or {}).get("nodes") or []
    return [k for c in comments if login(c) == bot and (k := kind(c))]


def is_disputed(thread, bot):
    """Open, and the bot's latest verdict is a dispute: the author arguing on doesn't end it."""
    found = bot_kinds(thread, bot)
    return not thread["isResolved"] and bool(found) and found[-1] == "dispute"


def unresolvable(thread, bot):
    """Why `thread` can't be resolved, or None once the bot verified or withdrew it last."""
    comments = thread["comments"]["nodes"]
    last = comments[-1] if comments else None
    if last and login(last) == bot and kind(last) in ("verify", "withdraw"):
        return None
    found = bot_kinds(thread, bot)
    if found and found[-1] in BLOCKING:
        return BLOCKING[found[-1]]
    if last and kind(last):
        return (f"its last comment is a {KINDS[kind(last)]} written by "
                f"{login(last) or 'a deleted account'}, not the bot")
    if found:
        return f"has a comment after the bot's {KINDS[found[-1]]}"
    return "has no verification or withdrawal from the bot"


def check_resolvable(response, ids, bot):
    """Refuse, naming each failing thread and why, unless every one of `ids` can be resolved."""
    if not bot:
        raise Refusal("no reviewer app is set up, so no thread can carry the bot's verification: "
                      "run scripts/reviewer-setup.py once")
    by_id = {t["id"]: t for t in nodes(response)}
    failed = []
    for id in ids:
        why = unresolvable(by_id[id], bot) if id in by_id else "isn't a review thread on this PR"
        if why:
            failed.append(f"{id} {why}")
    if failed:
        raise Refusal("resolved nothing; a thread resolves once its last comment is the bot's "
                      "verification or withdrawal:\n" + "\n".join(failed))
