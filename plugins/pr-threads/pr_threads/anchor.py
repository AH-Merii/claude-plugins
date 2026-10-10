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
    # pulling would merge a rewritten PR's old commits back in, and pushing would undo it
    own = own_commits(repo, local, pr_head)
    if own:
        raise NotPulled(f"{branch} and the PR head {pr_head[:12]} have diverged, and {branch} has "
                        f"commits the PR doesn't ({', '.join(c[:12] for c in own)}): rebase them "
                        f"onto the PR head (git rebase {pr_head[:12]}), or keep them on another "
                        "branch and check out the PR head")
    raise NotPulled(f"the PR was rewritten (amended, rebased or force-pushed) since {branch} "
                    f"checked it out. Don't pull or push; reset {branch} to the PR head "
                    f"(git reset --keep {pr_head[:12]}), or check it out with gh pr checkout")


def own_commits(repo, local, pr_head):
    """Local commits the PR never had: no copy in the PR head, and not on any remote.

    The commits a rewrite replaced have a copy (same patch) in the PR or were pushed, so
    they aren't the clone's own work.
    """
    out = git(repo, "rev-list", "--cherry-pick", "--right-only", "--no-merges",
              f"{pr_head}...{local}", "--not", "--remotes")
    return out.stdout.split()


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def renamed_from(repo, base, head, path):
    """The path `path` had at the merge base if the PR renamed it, else None."""
    out = git(repo, "diff", "--name-status", "-M", "-z", f"{base}...{head}", check=False)
    fields = iter(out.stdout.split("\0"))
    for status in fields:  # each entry is a status, then one path, or two for a rename or copy
        paths = (next(fields, ""), next(fields, "")) if status[:1] in ("R", "C") else (next(fields, ""),)
        if status[:1] == "R" and paths[1] == path:
            return paths[0]
    return None


def hunks(repo, base, head, path):
    """Head-side line ranges of the PR diff for `path`, diffed from the merge base like GitHub.

    Like GitHub, a renamed file shows only its changed hunks, not every line as added.
    """
    old = renamed_from(repo, base, head, path)
    out = git(repo, "diff", "--no-color", "--no-ext-diff", "-M", "-U3", f"{base}...{head}", "--",
              *([old] if old else []), path, check=False)
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
