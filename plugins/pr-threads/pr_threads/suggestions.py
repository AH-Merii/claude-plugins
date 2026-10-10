"""GitHub's ```suggestion blocks: write them, read them back, and apply one to the local file."""
import os
import re

from pr_threads import Refusal
from pr_threads.anchor import git


class StaleSuggestion(Refusal):
    pass


def suggestion_body(text, replacement):
    """`text` plus a suggestion replacing the commented lines with `replacement`."""
    if replacement and not replacement.endswith("\n"):
        replacement += "\n"
    longest = max((len(run) for run in re.findall(r"`+", replacement)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{text}\n\n{fence}suggestion\n{replacement}{fence}\n"


OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)")


def parse_suggestion(body):
    """The replacement in the first ```suggestion block of `body`, or None if there isn't one."""
    lines = body.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        fence, info = m.groups()
        close = re.compile(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
        j = next((k for k in range(i + 1, len(lines)) if close.match(lines[k])), None)
        if j is None:
            return None
        if info == "suggestion":
            return "".join(line + "\n" for line in lines[i + 1:j])
        i = j + 1
    return None


LOCAL_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@", re.M)


def follow(repo, commit, path, start, end):
    """Where lines start..end of `path` at `commit` are in the local file now, or None.

    The lines are followed through the diff from `commit` to the working tree, so edits
    elsewhere only shift them. None if any of them changed: a copy of their text elsewhere
    is other code. The histogram diff anchors on unique lines, so it doesn't mistake a
    copy for the original.
    """
    out = git(repo, "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
              "--diff-algorithm=histogram", "-U0", commit, "--", path)
    shift = 0
    for old, old_n, new_n in LOCAL_HUNK.findall(out.stdout):
        old, old_n, new_n = int(old), int(old_n or 1), int(new_n or 1)
        # a hunk removing nothing inserts after line `old`
        first, last = (old + 1, old) if old_n == 0 else (old, old + old_n - 1)
        if last < start:
            shift += new_n - old_n
        elif first > end:
            break
        else:
            return None
    return start + shift


def accept(repo, commit, path, start, end, replacement):
    """Replace lines start..end of `path`, as they were at `commit`, with `replacement`.

    The lines are found where local edits since `commit` moved them. Refused, leaving the
    file alone, if those lines themselves changed. Every other byte stays as it was: line
    endings, and a missing final newline.
    """
    shown = git(repo, "show", f"{commit}:{path}", check=False)
    if shown.returncode:
        raise StaleSuggestion(f"can't read {path} at the reviewed commit {commit[:12]}: fetch it first")
    file = os.path.join(repo, path)
    try:
        with open(file, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        raise StaleSuggestion(f"{path} no longer exists locally") from None
    at = None
    if len(shown.stdout.splitlines()) >= end:
        at = follow(repo, commit, path, start, end)
    if at is None:
        raise StaleSuggestion(f"{path}:{start}-{end} changed since the review at {commit[:12]}, "
                              "so the suggestion no longer applies: make the change by hand")
    lines = re.findall(rb"[^\n]*\n|[^\n]+\Z", data)
    new = replacement.encode()
    ends = [line for line in lines if line.endswith(b"\n")]
    if ends and all(line.endswith(b"\r\n") for line in ends):
        new = new.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    out = b"".join(lines[:at - 1] + [new] + lines[at - 1 + end - start + 1:])
    if not data.endswith(b"\n") and out.endswith(b"\n"):
        out = out[:-2] if out.endswith(b"\r\n") else out[:-1]
    with open(file, "wb") as f:
        f.write(out)
