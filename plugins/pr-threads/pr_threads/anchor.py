"""Pin a local path:line to a line GitHub accepts in the PR diff, or refuse up front."""
import re
import subprocess

from pr_threads import Refusal


class NotInDiff(Refusal):
    pass


class LocalDiffers(Refusal):
    pass


class NotPushed(Refusal):
    pass


class NotPulled(Refusal):
    pass


def git(repo, *args, check=True):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and out.returncode:
        raise Refusal(f"git {args[0]}: {out.stderr.strip()}")
    return out


def has_commit(repo, sha):
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def is_ancestor(repo, a, b):
    return git(repo, "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def check_synced(repo, branch, pr_head):
    """Refuse unless the local branch (else HEAD) is exactly the pushed PR head."""
    if not has_commit(repo, pr_head):
        raise NotPulled(f"the PR head {pr_head[:12]} isn't in this clone: fetch and pull it first")
    local = git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}^{{commit}}", check=False)
    local = local.stdout.strip() or git(repo, "rev-parse", "HEAD").stdout.strip()
    if local == pr_head:
        return
    if is_ancestor(repo, pr_head, local):
        raise NotPushed(f"{branch} has commits the PR doesn't: push them first, "
                        "so line numbers match what GitHub shows")
    if is_ancestor(repo, local, pr_head):
        raise NotPulled(f"{branch} is behind the PR head {pr_head[:12]}: pull first")
    raise NotPulled(f"{branch} and the PR head {pr_head[:12]} have diverged: pull, then push")


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def hunks(repo, base, head, path):
    """Head-side line ranges of the PR diff for `path`, diffed from the merge base like GitHub."""
    out = git(repo, "diff", "--no-color", "--no-ext-diff", "-U3", f"{base}...{head}", "--", path,
              check=False)
    if out.returncode:
        raise NotPulled(f"can't diff the PR locally: fetch its base and head ({out.stderr.strip()})")
    return [(int(s), int(s) + int(n if n is not None else 1) - 1) for s, n in HUNK.findall(out.stdout)]


def anchor(repo, base, head, path, start, end=None):
    """GitHub's coordinates for lines start..end of `path` at `head`, on the new side."""
    end = end or start
    if git(repo, "diff", "--quiet", head, "--", path, check=False).returncode:
        raise LocalDiffers(f"{path} has uncommitted local changes, so its line numbers no longer "
                           "match the PR head: commit and push them, or stash them")
    ranges = hunks(repo, base, head, path)
    if not any(lo <= start <= end <= hi for lo, hi in ranges):
        where = ", ".join(f"{lo}-{hi}" for lo, hi in ranges) or "none, the PR doesn't change it"
        raise NotInDiff(f"{path}:{start}-{end} isn't inside one hunk of the PR diff "
                        f"(commentable lines: {where})")
    pinned = {"path": path, "line": end, "side": "RIGHT"}
    if start != end:
        pinned.update(start_line=start, start_side="RIGHT")
    return pinned
