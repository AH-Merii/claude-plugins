"""pr-threads verbs: review a PR as the bot, and work through its threads as the author."""
import argparse
import json
import os
import re
import sys

from pr_threads import Refusal, gh, verdicts
from pr_threads.anchor import anchor, check_synced, git, has_commit, is_ancestor
from pr_threads.status import handoff, render as render_status
from pr_threads.suggestions import accept, parse_suggestion, suggestion_body
from pr_threads.threads import FIELDS, nodes, open_threads, render as render_threads

EVENTS = {"pass": "APPROVE", "changes": "REQUEST_CHANGES"}
# the bot's verdicts given with a reason -> (how its reply opens, what the reason records, help)
REASONED = {
    "withdraw": ("Withdrawn", "why the finding was dropped", "drop a finding after the author's pushback"),
    "dispute": ("Disputed", "why the finding stands", "keep a finding against the author's pushback"),
    "reopen": ("Reopened", "why the fix didn't work", "reopen a thread the author says is fixed"),
}


# --- staged review comments, kept per repo and PR until submit succeeds ---

def staged_path(repo, number):
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(state, "pr-threads", repo, f"{number}.json")


def load_staged(repo, number):
    try:
        with open(staged_path(repo, number)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"head": None, "comments": []}


def save_staged(repo, number, staged):
    path = staged_path(repo, number)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(staged, f, indent=2)
    os.replace(path + ".tmp", path)


# --- shared steps ---

def check_files(items):
    """Refuse before anything is uploaded or sent if any `path[#alt]` isn't a file."""
    for item in items:
        path = item.partition("#")[0]
        if not os.path.isfile(path):
            raise Refusal(f"--attach {path}: no such file")


def attachments(items):
    """Upload each `path[#alt]` as the user, in order; markdown images for the body."""
    check_files(items)
    pairs = [(path, alt or os.path.basename(path)) for path, _, alt in (i.partition("#") for i in items)]
    return [f"![{alt}]({gh.upload(path)})" for path, alt in pairs]


def with_images(text, images):
    return "\n\n".join([text, "\n".join(images)]) if images else text


def parse_location(text):
    m = re.fullmatch(r"(.+):(\d+)(?:-(\d+))?", text)
    if not m:
        raise Refusal(f"{text}: expected path:line or path:start-end")
    start, end = int(m[2]), int(m[3] or m[2])
    if end < start:
        raise Refusal(f"{text}: the range ends before it starts")
    return m[1], start, end


def toplevel():
    return git(".", "rev-parse", "--show-toplevel").stdout.strip()


# --- reviewer ---

def stage(args, replacement=None):
    path, start, end = parse_location(args.location)
    check_files(args.attach)
    repo = gh.repo()
    pr = gh.pull_request(args.pr)
    staged = load_staged(repo, pr["number"])
    if staged["comments"] and staged["head"] != pr["headRefOid"]:
        raise Refusal(f"the PR head moved to {pr['headRefOid'][:12]} since the staged comments were "
                      f"pinned on {staged['head'][:12]}: send them with `pr-threads submit changes`, "
                      "or drop them with `pr-threads discard`, before adding more")
    root = toplevel()
    check_synced(root, pr["headRefName"], pr["headRefOid"])
    rel = os.path.relpath(os.path.abspath(path), root)
    pinned = anchor(root, pr["baseRefOid"], pr["headRefOid"], rel, start, end)
    # upload last: nothing may refuse after it, since an uploaded image can't be deleted
    text = with_images(args.body, attachments(args.attach))
    pinned["body"] = text if replacement is None else suggestion_body(text, replacement)
    staged = {"head": pr["headRefOid"], "comments": staged["comments"] + [pinned]}
    save_staged(repo, pr["number"], staged)
    print(f"staged {args.location} ({len(staged['comments'])} pending); "
          "nothing is posted until submit")


def cmd_comment(args):
    stage(args)


def replacement(args):
    """The suggested lines, from stdin or --replacement, never both; empty only with --delete."""
    flag = "--delete" if args.delete else "--replacement" if args.replacement is not None else None
    piped = "" if flag and sys.stdin.isatty() else sys.stdin.read()
    if flag and piped:
        raise Refusal(f"replacement lines came on stdin and with {flag}: pick one")
    text = "" if args.delete else piped if args.replacement is None else args.replacement
    if not text and not args.delete:
        raise Refusal("the replacement is empty: give it on stdin or with --replacement, "
                      "or pass --delete to suggest deleting the lines")
    return text


def cmd_suggest(args):
    stage(args, replacement=replacement(args))


def cmd_submit(args):
    repo = gh.repo()
    token = gh.bot_token(repo)
    pr = gh.pull_request(args.pr)
    staged = load_staged(repo, pr["number"])
    if args.verdict == "pass" and staged["comments"] and staged["head"] != pr["headRefOid"]:
        # changes may still go out on the staged head: asking for changes there approves nothing
        raise Refusal(f"the PR head moved to {pr['headRefOid'][:12]} since the staged comments were "
                      f"pinned on {staged['head'][:12]}, so a pass would approve commits nobody "
                      "reviewed: submit `changes` on the staged head, or drop the comments with "
                      "`pr-threads discard` and review the new head")
    review = {"commit_id": staged["head"] if staged["comments"] else pr["headRefOid"],
              "event": EVENTS[args.verdict],
              "body": with_images(args.body, attachments(args.attach))}
    if staged["comments"]:
        review["comments"] = staged["comments"]
    try:
        url = gh.submit_review(repo, pr["number"], review, token)
    except gh.GhError as e:
        if not staged["comments"]:
            raise
        raise Refusal(f"{e}\nthe staged comments are kept: fix the cause and submit again, or "
                      "if GitHub rejects them, drop them with `pr-threads discard`") from None
    if staged["comments"]:
        os.remove(staged_path(repo, pr["number"]))
    print(f"submitted {args.verdict} with {len(staged['comments'])} comments: {url}")


def cmd_discard(args):
    repo, number = gh.repo(), pr_number(args)
    count = len(load_staged(repo, number)["comments"])
    if count:
        os.remove(staged_path(repo, number))
    print(f"discarded {count} staged comment{'' if count == 1 else 's'} on PR {number}")


def bot_reply(thread, kind, text):
    """Post a verdict in `thread` as the bot, or refuse with the install link."""
    token = gh.bot_token(gh.repo())
    print(gh.reply(thread, verdicts.body(kind, text), token))


def cmd_verify(args):
    pr = gh.pull_request(args.pr)
    root, head = toplevel(), pr["headRefOid"]
    if not has_commit(root, head):
        raise Refusal(f"the PR head {head[:12]} isn't in this clone: fetch it, so {args.sha} "
                      "can be checked against it")
    sha = git(root, "rev-parse", "--verify", "-q", f"{args.sha}^{{commit}}", check=False).stdout.strip()
    if not sha or not is_ancestor(root, sha, head):
        raise Refusal(f"{args.sha} isn't in the history of the PR head {head[:12]} on GitHub, so "
                      "it can't hold the fix: push it first, or name a commit of the PR")
    bot_reply(args.thread, "verify", f"Verified in {sha}." + (f" {args.note}" if args.note else ""))


def cmd_reasoned(args):
    opening, records, _ = REASONED[args.verb]
    if not args.reason.strip():
        raise Refusal(f"{args.verb} needs a reason: it's the record of {records}")
    bot_reply(args.thread, args.verb, f"{opening}: {args.reason}")


def cmd_resolve(args):
    response = gh.review_threads(gh.repo(), pr_number(args), verdicts.FIELDS)
    verdicts.check_resolvable(response, args.threads, verdicts.bot_slug())
    gh.resolve(args.threads)
    print(f"resolved {', '.join(args.threads)}")


# --- author ---

def pr_number(args):
    return args.pr or gh.pull_request()["number"]


def cmd_threads(args):
    found = open_threads(gh.review_threads(gh.repo(), pr_number(args), FIELDS))
    print(json.dumps(found, indent=2) if args.json else render_threads(found))


def cmd_reply(args):
    body = with_images(args.body, attachments(args.attach))
    print(gh.reply(args.thread, body))


def cmd_accept(args):
    response = gh.review_threads(gh.repo(), pr_number(args), FIELDS)
    thread = next((t for t in nodes(response) if t["id"] == args.thread), None)
    if thread is None:
        raise Refusal(f"no review thread {args.thread} on this PR")
    comments = thread["comments"]["nodes"]
    replacement = next((s for c in reversed(comments)
                        if (s := parse_suggestion(c["body"])) is not None), None)
    if replacement is None:
        raise Refusal(f"thread {args.thread} has no suggestion to accept")
    commit = (comments[0].get("originalCommit") or {}).get("oid")
    if not commit:
        raise Refusal(f"thread {args.thread} doesn't say which commit it was written on")
    end = thread["originalLine"]
    start = thread["originalStartLine"] or end
    accept(toplevel(), commit, thread["path"], start, end, replacement)
    print(f"applied the suggestion from {args.thread} to {thread['path']}:{start}-{end}; "
          "commit it as part of your fix")


def cmd_post(args):
    check_files(args.attach)
    print(gh.post(args.number, args.body, args.attach))


# --- either side ---

def cmd_status(args):
    repo, number = gh.repo(), pr_number(args)
    got = handoff(gh.review_threads(repo, number, verdicts.FIELDS), gh.reviews(repo, number),
                  verdicts.bot_slug())
    print(json.dumps(got) if args.json else render_status(got))


def parser():
    p = argparse.ArgumentParser(prog="pr-threads", description=__doc__)
    p.add_argument("--pr", type=int, help="PR number (default: the current branch's PR)")
    verbs = p.add_subparsers(dest="verb", required=True)

    def verb(name, func, help, attach=False):
        v = verbs.add_parser(name, help=help)
        v.set_defaults(func=func)
        if attach:
            v.add_argument("--attach", action="append", default=[], metavar="FILE[#ALT]",
                           help="image or GIF to embed, uploaded with your login (repeatable)")
        return v

    v = verb("comment", cmd_comment, "stage a comment on path:line[-end]", attach=True)
    v.add_argument("location")
    v.add_argument("body")
    v = verb("suggest", cmd_suggest, "stage a suggested change; replacement on stdin", attach=True)
    v.add_argument("location")
    v.add_argument("body")
    lines = v.add_mutually_exclusive_group()
    lines.add_argument("--replacement", metavar="TEXT", help="the replacement, instead of stdin")
    lines.add_argument("--delete", action="store_true", help="suggest deleting the lines")
    v = verb("submit", cmd_submit, "post the staged comments as one review, as the bot", attach=True)
    v.add_argument("verdict", choices=EVENTS)
    v.add_argument("body")
    verb("discard", cmd_discard, "drop this PR's staged comments")
    v = verb("verify", cmd_verify, "say as the bot that a thread's fix is in a commit of the PR")
    v.add_argument("thread")
    v.add_argument("sha")
    v.add_argument("note", nargs="?")
    for name, (_, records, help) in REASONED.items():
        v = verb(name, cmd_reasoned, f"{help}, as the bot, with {records}")
        v.add_argument("thread")
        v.add_argument("reason")
    v = verb("resolve", cmd_resolve, "resolve threads the bot verified or withdrew, as you, in one request")
    v.add_argument("threads", nargs="+")
    v = verb("threads", cmd_threads, "list open threads at local path:line")
    v.add_argument("--json", action="store_true")
    v = verb("reply", cmd_reply, "reply to a thread as you", attach=True)
    v.add_argument("thread")
    v.add_argument("body")
    v = verb("accept", cmd_accept, "apply a thread's suggestion to the local file")
    v.add_argument("thread")
    v = verb("post", cmd_post, "general comment on an issue or PR conversation, as you", attach=True)
    v.add_argument("number", type=int)
    v.add_argument("body")
    v = verb("status", cmd_status, "handoff state (pending, changes, approved or pass), disputes and round")
    v.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except Refusal as e:
        print(f"pr-threads: {e}", file=sys.stderr)
        return 1
    return 0
