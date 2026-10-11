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


def git(repo, *args, check=True, input=None):
    out = subprocess.run(["git", "-C", repo, *args], input=input, capture_output=True, text=True, check=False)
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
    if is_ancestor(repo, local, pr_head):
        raise NotPulled(f"{branch} is behind the PR head {pr_head[:12]}: pull first")
    own = own_commits(repo, local, pr_head)
    ahead = git(repo, "rev-list", "--no-merges", f"{pr_head}..{local}").stdout.split()
    if is_ancestor(repo, pr_head, local) and set(own) == set(ahead):
        raise NotPushed(
            f"{branch} has commits the PR doesn't: push them first, so line numbers match what GitHub shows"
        )
    # the PR was rewritten: pulling would merge the commits it replaced back in, pushing
    # would undo it, and a plain rebase would replay them onto their replacements
    if own:
        raise NotPulled(
            f"{branch} and the PR head {pr_head[:12]} have diverged, and {branch} has "
            f"commits the PR doesn't ({', '.join(c[:12] for c in own)}): rebase just "
            f"those onto the PR head (git rebase --onto {pr_head[:12]} {own[-1][:12]}^), "
            "or keep them on another branch and check out the PR head"
        )
    raise NotPulled(
        f"the PR was rewritten (amended, rebased or force-pushed) since {branch} "
        f"checked it out. Don't pull or push; reset {branch} to the PR head "
        f"(git reset --keep {pr_head[:12]}), or check it out with gh pr checkout"
    )


def own_commits(repo, local, pr_head):
    """Local commits the PR never had, newest first: no copy (same patch) in the PR head, and
    not got from a remote.

    Commits a rewrite replaced came from a fetch, a pull or a push, so they aren't the
    clone's own work. Its own commits stay its own however they were moved since, by a
    rebase or a pull --rebase, or made without a reflog entry of their own (GitButler).
    """
    candidates = git(
        repo, "rev-list", "--cherry-pick", "--right-only", "--no-merges", f"{pr_head}...{local}"
    ).stdout.split()
    revs = [local, f"^{pr_head}", *(f"^{tip}" for tip in received(repo))]
    unreceived = git(repo, "rev-list", "--ignore-missing", "--stdin", input="\n".join(revs))
    unreceived = set(unreceived.stdout.split())
    return [c for c in candidates if c in unreceived]


# reflog subjects of a local ref update that brought commits in from a remote: a fetch or clone
# into the ref, a pull's fast-forward, a fast-forward to FETCH_HEAD (which the reflog records
# as a bare commit id, as rerunning gh pr checkout makes), and the upstream a pull rebases onto
FETCHED = re.compile(
    r"(?:fetch|clone)\b|(?:pull\b.*|merge [0-9a-f]{40,64}): Fast-forward$"
    r"|pull\b.*\(start\): checkout "
)
# a branch started from a remote-tracking branch, as checking out a PR branch does
CREATED = re.compile(r"branch: Created from (?:refs/remotes/|([^/\s]+)/)")


def received(repo):
    """Every commit this clone got from a remote or pushed to one, as tips read off its reflogs.

    A reflog entry lasts 90 days by default; without reflogs only the remote-tracking
    branches count.
    """
    remotes = set(git(repo, "remote").stdout.split())
    tips = git(repo, "for-each-ref", "--format=%(objectname)", "refs/remotes").stdout.split()
    log = git(repo, "log", "-g", "--all", "--format=%H %gD %gs", check=False).stdout
    for sha, ref, subject in (line.split(" ", 2) for line in log.splitlines()):
        created = CREATED.match(subject)
        if (
            ref.startswith("refs/remotes/")
            or FETCHED.match(subject)
            or (created and (created[1] is None or created[1] in remotes))
        ):
            tips.append(sha)
    return tips


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


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
    out = git(
        repo,
        "diff",
        "--no-color",
        "--no-ext-diff",
        "-M",
        "-U3",
        f"{base}...{head}",
        "--",
        *([old] if old else []),
        path,
        check=False,
    )
    if out.returncode:
        raise NotPulled(f"can't diff the PR locally: fetch its base and head ({out.stderr.strip()})")
    return [(int(s), int(s) + int(n if n is not None else 1) - 1) for s, n in HUNK.findall(out.stdout)]


def anchor(repo, base, head, path, start, end=None):
    """GitHub's coordinates for lines start..end of `path` at `head`, on the new side."""
    end = end or start
    if git(repo, "diff", "--quiet", head, "--", path, check=False).returncode:
        raise LocalDiffers(
            f"{path} has uncommitted local changes, so its line numbers no longer "
            "match the PR head: commit and push them, or stash them"
        )
    ranges = hunks(repo, base, head, path)
    if not any(lo <= start <= end <= hi for lo, hi in ranges):
        where = ", ".join(f"{lo}-{hi}" for lo, hi in ranges) or "none, the PR doesn't change it"
        raise NotInDiff(f"{path}:{start}-{end} isn't inside one hunk of the PR diff (commentable lines: {where})")
    pinned = {"path": path, "line": end, "side": "RIGHT"}
    if start != end:
        pinned.update(start_line=start, start_side="RIGHT")
    return pinned
