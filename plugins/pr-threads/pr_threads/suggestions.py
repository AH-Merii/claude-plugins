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


def accept(repo, commit, path, start, end, replacement):
    """Replace lines start..end of `path`, as they were at `commit`, with `replacement`.

    Refused, leaving the file alone, unless the local file still has those exact lines at
    those exact line numbers.
    """
    shown = git(repo, "show", f"{commit}:{path}", check=False)
    if shown.returncode:
        raise StaleSuggestion(f"can't read {path} at the reviewed commit {commit[:12]}: fetch it first")
    target = shown.stdout.splitlines(keepends=True)[start - 1:end]
    file = os.path.join(repo, path)
    try:
        with open(file) as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise StaleSuggestion(f"{path} no longer exists locally") from None
    if lines[start - 1:end] != target or len(target) != end - start + 1:
        raise StaleSuggestion(f"{path}:{start}-{end} changed since the review at {commit[:12]}, "
                              "so the suggestion no longer applies: make the change by hand")
    with open(file, "w") as f:
        f.writelines(lines[:start - 1] + [replacement] + lines[end:])
