"""#7: local path:line is pinned to a line GitHub accepts in the PR diff, or refused up front."""

import os
import re
import shlex
import subprocess
import tempfile
import unittest
from typing import ClassVar

from helpers import (
    Repo,
    advises,
    assert_keeps_local_work,
    assert_moves_to_pr_head,
    clean_env,
    git,
    isolate_git,
    numbered,
)
from pr_threads import Refusal
from pr_threads.anchor import LocalDiffers, NotInDiff, NotPulled, NotPushed, anchor, check_synced


class AnchorTest(unittest.TestCase):
    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def pin(self, path, start, end=None, base=None):
        return anchor(self.repo.path, base or self.repo.base, self.repo.head, path, start, end)

    def assertPinned(self, got, line, start=None):
        self.assertEqual((got["path"], got["line"], got["side"]), ("app.py", line, "RIGHT"))
        if start is not None:
            self.assertEqual((got["start_line"], got["start_side"]), (start, "RIGHT"))

    def test_changed_line_is_pinned_on_the_new_side(self):
        self.assertPinned(self.pin("app.py", 10), 10)

    def test_every_line_inside_a_hunk_is_accepted(self):
        for line in (7, 13, 18, 25):
            with self.subTest(line=line):
                self.assertPinned(self.pin("app.py", line), line)

    def test_lines_outside_every_hunk_are_refused(self):
        for line in (1, 6, 14, 17, 26, 32):
            with self.subTest(line=line), self.assertRaises(NotInDiff):
                self.pin("app.py", line)

    def test_range_inside_one_hunk_becomes_a_multi_line_comment(self):
        self.assertPinned(self.pin("app.py", 21, 22), 22, start=21)

    def test_range_spanning_two_hunks_is_refused(self):
        with self.assertRaises(NotInDiff):
            self.pin("app.py", 12, 21)

    def test_file_untouched_by_the_pr_is_refused(self):
        with self.assertRaises(NotInDiff):
            self.pin("other.py", 1)

    def test_lines_only_the_base_branch_changed_are_refused(self):
        # GitHub diffs against the merge base, so main moving on adds nothing to the PR
        git(self.repo.path, "checkout", "-q", "main")
        self.repo.write("app.py", self.repo.read("app.py").replace("line 2\n", "main 2\n"))
        git(self.repo.path, "commit", "-qam", "main moves on")
        new_base = git(self.repo.path, "rev-parse", "HEAD")
        git(self.repo.path, "checkout", "-q", "feature")
        with self.assertRaises(NotInDiff):
            self.pin("app.py", 2, base=new_base)
        self.assertPinned(self.pin("app.py", 10, base=new_base), 10)

    def test_uncommitted_edit_to_the_file_is_refused(self):
        # Line numbers the caller sees no longer match the PR head
        self.repo.write("app.py", "inserted\n" + self.repo.read("app.py"))
        with self.assertRaises(LocalDiffers):
            self.pin("app.py", 10)

    def test_uncommitted_edit_to_another_file_does_not_matter(self):
        self.repo.write("other.py", "edited\n")
        self.assertEqual(self.pin("app.py", 10)["line"], 10)


class RenameTest(unittest.TestCase):
    """Anchoring reads the diff GitHub shows, which follows renames.

    A renamed file is not a wholly added one: GitHub shows only its changed hunks, so only
    those lines are commentable, wherever the file moved. Each file here has 40 lines
    (`<name> 1` .. `<name> 40`) at base, and the PR renames it.
    """

    # new path: (what the PR does to it, lines GitHub shows, lines outside every hunk)
    RENAMES: ClassVar = {
        "pure2.txt": ("renamed, unchanged", [], [1, 20, 40]),
        "tail2.txt": ("renamed, a line appended", [38, 41], [1, 2, 37]),
        "mid2.txt": ("renamed, line 20 changed", [17, 20, 23], [1, 16, 24, 40]),
        "sub/into.txt": ("moved into a directory, line 20 changed", [17, 20, 23], [1, 16, 24, 40]),
        "out.txt": ("moved out of a directory, a line appended", [38, 41], [1, 2, 37]),
    }

    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        path = self.repo.path
        git(path, "checkout", "-q", "main")
        os.mkdir(os.path.join(path, "sub2"))
        for name, old in [
            ("pure", "pure.txt"),
            ("tail", "tail.txt"),
            ("mid", "mid.txt"),
            ("into", "into.txt"),
            ("out", "sub2/out.txt"),
        ]:
            self.repo.write(old, "".join(f"{name} {i}\n" for i in range(1, 41)))
        git(path, "add", ".")
        git(path, "commit", "-qm", "files to rename")
        self.base = git(path, "rev-parse", "HEAD")
        git(path, "checkout", "-q", "-B", "feature")
        os.mkdir(os.path.join(path, "sub"))
        for old, new in [
            ("pure.txt", "pure2.txt"),
            ("tail.txt", "tail2.txt"),
            ("mid.txt", "mid2.txt"),
            ("into.txt", "sub/into.txt"),
            ("sub2/out.txt", "out.txt"),
        ]:
            git(path, "mv", old, new)
        self.repo.write("tail2.txt", self.repo.read("tail2.txt") + "tail 41\n")
        self.repo.write("out.txt", self.repo.read("out.txt") + "out 41\n")
        self.repo.write("mid2.txt", self.repo.read("mid2.txt").replace("mid 20\n", "MID 20\n"))
        self.repo.write("sub/into.txt", self.repo.read("sub/into.txt").replace("into 20\n", "INTO 20\n"))
        git(path, "commit", "-qam", "rename them")
        self.head = git(path, "rev-parse", "HEAD")

    def test_only_lines_github_shows_for_a_renamed_file_are_commentable(self):
        for path, (what, shown, hidden) in self.RENAMES.items():
            for line in shown:
                with self.subTest(what, line=line, expect="pinned"):
                    got = anchor(self.repo.path, self.base, self.head, path, line)
                    self.assertEqual((got["path"], got["line"], got["side"]), (path, line, "RIGHT"))
            for line in hidden:
                with self.subTest(what, line=line, expect="refused"), self.assertRaises(NotInDiff):
                    anchor(self.repo.path, self.base, self.head, path, line)


class SyncTest(unittest.TestCase):
    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def test_only_the_branch_at_the_pr_head_is_accepted(self):
        check_synced(self.repo.path, "feature", self.repo.head)
        # the same branch against an older PR head is a commit ahead of it
        with self.assertRaises(NotPushed):
            check_synced(self.repo.path, "feature", self.repo.base)

    def test_unpushed_local_commit_is_refused(self):
        self.repo.write("other.py", "more\n")
        git(self.repo.path, "commit", "-qam", "local only")
        with self.assertRaises(NotPushed) as caught:
            check_synced(self.repo.path, "feature", self.repo.head)
        self.assertIn("push", str(caught.exception).lower())

    # behind is a different fix from ahead: the user pulls, not pushes
    def test_branch_behind_the_pr_head_is_refused(self):
        self.repo.write("other.py", "pushed from elsewhere\n")
        git(self.repo.path, "commit", "-qam", "pushed from elsewhere")
        pr_head = git(self.repo.path, "rev-parse", "HEAD")
        git(self.repo.path, "reset", "-q", "--hard", self.repo.head)
        with self.assertRaises(NotPulled) as caught:
            check_synced(self.repo.path, "feature", pr_head)
        self.assertNotIsInstance(caught.exception, NotPushed)
        self.assertIn("pull", str(caught.exception).lower())

    def diverged(self):
        """(name, PR head) for each way the PR head and the local branch can part ways."""
        path, local = self.repo.path, self.repo.head
        cases = []
        # the author amended the reviewed commit and force-pushed
        git(path, "commit", "-q", "--amend", "-m", "head, reworded")
        cases.append(("amended", git(path, "rev-parse", "HEAD")))
        # the author rebased the PR onto a newer main
        git(path, "checkout", "-q", "main")
        self.repo.write("other.py", "main moved on\n")
        git(path, "commit", "-qam", "main moves on")
        git(path, "checkout", "-q", "-B", "rebased", local)
        git(path, "rebase", "-q", "main")
        cases.append(("rebased", git(path, "rev-parse", "HEAD")))
        # the PR moved on while this clone made its own commit
        git(path, "checkout", "-q", "-B", "remote", local)
        self.repo.write("app.py", self.repo.read("app.py") + "pushed from elsewhere\n")
        git(path, "commit", "-qam", "pushed from elsewhere")
        cases.append(("both moved", git(path, "rev-parse", "HEAD")))
        git(path, "checkout", "-q", "feature")
        git(path, "reset", "-q", "--hard", local)
        self.repo.write("other.py", "local only\n")
        git(path, "commit", "-qam", "local only")
        return cases, git(path, "rev-parse", "HEAD")

    def test_diverged_branch_is_told_how_to_get_back_without_pulling(self):
        """A rewritten PR head means reset to it; the clone's own commits mean rebase them."""
        cases, local_commit = self.diverged()
        for name, pr_head in cases:
            with self.subTest(name):
                # only "both moved" keeps the local commit; the others diverge from the reviewed head
                git(self.repo.path, "reset", "-q", "--hard", local_commit if name == "both moved" else self.repo.head)
                with self.assertRaises(Refusal) as caught:
                    check_synced(self.repo.path, "feature", pr_head)
                if name == "both moved":
                    assert_keeps_local_work(self, str(caught.exception), local_commit)
                else:
                    assert_moves_to_pr_head(self, str(caught.exception))

    def test_advice_is_told_apart_from_a_mention(self):
        # the checks above ban the advice to pull or push, not the words
        for message, verb, advice in [
            ("feature and the PR head abc1234 have diverged: pull, then push", "pull", True),
            ("feature and the PR head abc1234 have diverged: pull, then push", "push", True),
            ("behind the PR head: pull first", "pull", True),
            ("run `git pull` and retry", "pull", True),
            ("Pull the PR head, then retry", "pull", True),
            ("don't pull or push; reset to it", "pull", False),
            ("don't pull or push; reset to it", "push", False),
            ("don't pull or push; reset to it", "reset", True),
            ("the PR head was force-pushed", "push", False),
            ("the pull request head moved", "pull", False),
            ("move to it with gh pr checkout 5 --force", "checkout", True),
            ("You can reset to it", "reset", True),
            ("git switch --detach abc1234", "switch", True),
            ("reset to it, or pull and merge it", "pull", True),
        ]:
            with self.subTest(message=message, verb=verb):
                self.assertEqual(advises(message, verb), advice)

    def test_divergence_checks_tell_safe_advice_from_harmful(self):
        local = "abcdef1" + "0" * 33
        moves = assert_moves_to_pr_head
        keeps = lambda test, message: assert_keeps_local_work(test, message, local)
        for check, message, ok in [
            (moves, "the PR head was rewritten; don't pull or push: reset to it", True),
            (moves, "the PR head was rewritten: move to it with gh pr checkout 5 --force", True),
            (moves, "diverged: reset to it, or pull and merge it", False),
            (keeps, "your commit abcdef1 isn't in the PR: rebase it onto the PR head", True),
            (keeps, "abcdef1 isn't in the PR; check out the PR head on a new branch", True),
            (keeps, "abcdef1 isn't in the PR: reset to the PR head", False),
            (keeps, "abcdef1 isn't in the PR: gh pr checkout 5 --force", False),
            (keeps, "abcdef1 isn't in the PR: git checkout -B feature origin/feature", False),
        ]:
            with self.subTest(check="moves" if check is moves else "keeps", message=message):
                if ok:
                    check(self, message)
                else:
                    with self.assertRaises(AssertionError):
                        check(self, message)

    def test_pr_head_missing_locally_is_refused(self):
        with self.assertRaises(NotPulled) as caught:
            check_synced(self.repo.path, "feature", "0" * 40)
        self.assertNotIsInstance(caught.exception, NotPushed)
        self.assertRegex(str(caught.exception).lower(), r"\bfetch\b|\bpull\b")


class RemoteSyncTest(unittest.TestCase):
    """#7 in a clone that got the PR from a remote, the two ways a reviewer's clone does.

    The author pushes a two-commit PR (`one` changes app.py line 10, `two` line 20) to a bare
    repo standing in for GitHub, which also keeps it at refs/pull/5/head. The clone checks out
    the PR at `two`, and later fetches whatever the author pushed:

    - "tracking": the PR branch is on the remote, so the clone tracks origin/feature. After the
      fetch origin/feature is the PR head, and the commits a rewrite replaced are on no remote.
    - "pull ref": a PR from a fork, whose repo isn't a remote here. As `gh pr checkout` does
      (cli/cli pkg/cmd/pr/checkout/checkout.go, cmdsForMissingRemote), the clone fetches
      refs/pull/5/head into its branch, and later fetches it again to FETCH_HEAD. No
      remote-tracking ref ever holds the PR's commits.

    In the usual review loop the PR moves on before it's rewritten, and the clone follows it
    with a fast-forward: `git pull --ff-only` when tracking, or, as rerunning `gh pr checkout`
    does (checkout.go, syncBranchCmds), a fetch of the pull ref and `merge --ff-only FETCH_HEAD`.
    So each rewrite is tried on a clone at `two`, and on one fast-forwarded to a third commit.
    A clone with its own commits can't fast-forward; it follows the PR with `git pull --rebase`,
    which replays its commits onto the third, so that is tried too.
    """

    SHAPES = ("tracking", "pull ref")

    def setUp(self):
        isolate_git(self)

    def start(self, shape, fast_forwarded=False):
        self.shape = shape
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.origin = os.path.join(tmp.name, "origin.git")
        self.author = os.path.join(tmp.name, "author")
        self.clone = os.path.join(tmp.name, "clone")
        git(tmp.name, "init", "-q", "--bare", "-b", "main", self.origin)
        git(tmp.name, "clone", "-q", self.origin, self.author)
        git(self.author, "symbolic-ref", "HEAD", "refs/heads/main")
        self.write(self.author, "app.py", numbered(30))
        self.write(self.author, "other.py", numbered(5))
        git(self.author, "add", ".")
        git(self.author, "commit", "-qm", "base")
        self.base = git(self.author, "rev-parse", "HEAD")
        git(self.author, "push", "-q", "origin", "HEAD:main")
        git(self.author, "checkout", "-qb", "feature")
        self.one = self.commit(self.author, "one", "app.py", "line 10\n", "changed 10\n")
        self.reviewed = self.commit(self.author, "two", "app.py", "line 20\n", "changed 20\n")
        self.publish()
        git(tmp.name, "clone", "-q", self.origin, self.clone)
        if shape == "pull ref":
            git(self.clone, "fetch", "-q", "origin", "refs/pull/5/head:feature")
        git(self.clone, "checkout", "-q", "feature")
        if fast_forwarded:
            self.commit(self.author, "three", "app.py", "line 25\n", "changed 25\n")
            self.publish()
            self.fast_forward()
        # the PR as the clone last had it
        self.checked_out = git(self.clone, "rev-parse", "feature")

    def fast_forward(self):
        """Bring the clone's branch up to the PR head, as a reviewer does between rounds."""
        if self.shape == "tracking":
            git(self.clone, "pull", "-q", "--ff-only")
        else:
            git(self.clone, "fetch", "-q", "origin", "refs/pull/5/head")
            git(self.clone, "merge", "-q", "--ff-only", "FETCH_HEAD")

    @staticmethod
    def write(repo, name, text):
        with open(os.path.join(repo, name), "w") as f:
            f.write(text)

    @staticmethod
    def commit(repo, message, name, old, new):
        """Replace `old` with `new` in `name`, commit it, and return the commit."""
        with open(os.path.join(repo, name)) as f:
            text = f.read()
        RemoteSyncTest.write(repo, name, text.replace(old, new))
        git(repo, "commit", "-qam", message)
        return git(repo, "rev-parse", "HEAD")

    # ways the author rewrites the PR before force-pushing it
    def amend_message(self):
        git(self.author, "commit", "-q", "--amend", "-m", "two, reworded")

    def amend_content(self):
        self.write(
            self.author, "app.py", numbered(30).replace("line 10\n", "changed 10\n").replace("line 20\n", "fixed 20\n")
        )
        git(self.author, "commit", "-q", "--amend", "-a", "--no-edit")

    def amend_earlier(self):
        git(self.author, "checkout", "-q", "--detach", self.base)
        self.commit(self.author, "one", "app.py", "line 10\n", "fixed 10\n")
        git(self.author, "cherry-pick", self.reviewed)
        git(self.author, "checkout", "-q", "-B", "feature")

    def rebase(self):
        git(self.author, "checkout", "-q", "main")
        self.commit(self.author, "main moves on", "other.py", "line 3\n", "main 3\n")
        git(self.author, "push", "-q", "origin", "main")
        git(self.author, "checkout", "-q", "feature")
        git(self.author, "rebase", "-q", "main")

    def squash(self):
        git(self.author, "reset", "-q", "--soft", self.base)
        git(self.author, "commit", "-qm", "one and two")

    def drop_earlier(self):
        git(self.author, "rebase", "-q", "--onto", self.base, self.one)

    def drop_top(self):
        git(self.author, "reset", "-q", "--hard", self.one)

    REWRITES: ClassVar = [
        ("message-only amend", amend_message),
        ("content amend", amend_content),
        ("content amend of an earlier commit", amend_earlier),
        ("rebase onto a newer main", rebase),
        ("squash", squash),
        ("force-push dropping an earlier commit", drop_earlier),
        ("force-push dropping the top commit", drop_top),
    ]

    def publish(self, force=False):
        """Push the author's PR branch to GitHub: its head branch, if it lives there, and the pull ref."""
        refs = ["feature:refs/pull/5/head"] + (["feature"] if self.shape == "tracking" else [])
        git(self.author, "push", "-q", *(["-f"] if force else []), "origin", *refs)

    def rewrite(self, how):
        how(self)
        self.publish(force=True)

    def fetch(self):
        """Fetch the way a reviewer does, and return the PR head."""
        if self.shape == "tracking":
            git(self.clone, "fetch", "-q", "origin")
            return git(self.clone, "rev-parse", "origin/feature")
        git(self.clone, "fetch", "-q", "origin", "refs/pull/5/head")
        return git(self.clone, "rev-parse", "FETCH_HEAD")

    def cases(self):
        """(shape, fast-forwarded first, rewrite name, rewrite) for every combination."""
        return [(shape, ff, name, how) for shape in self.SHAPES for ff in (False, True) for name, how in self.REWRITES]

    # how a clone with its own commits followed the PR before the rewrite
    FOLLOWS = (
        "stayed at two",
        "fast-forwarded, then committed",
        "committed, then pulled with rebase",
        "committed, then pulled with pull.rebase=merges",
    )

    def follow_with_own_commits(self, how=("--rebase",)):
        """The PR moves on to `three`, and the clone rebases its own commits onto it with
        `git pull --rebase`. Returns the clone's own commits as they now are, oldest first."""
        self.commit(self.author, "three", "app.py", "line 25\n", "changed 25\n")
        self.publish()
        pull = ["-c", "pull.rebase=merges", "pull", "-q"] if how == "config" else ["pull", "-q", *how]
        git(self.clone, *pull, *([] if self.shape == "tracking" else ["origin", "refs/pull/5/head"]))
        self.checked_out = git(self.clone, "rev-parse", f"HEAD~{len(self.OWN)}")
        return git(self.clone, "rev-list", "--reverse", f"{self.checked_out}..HEAD").split()

    def refusal(self, pr_head):
        with self.assertRaises(Refusal) as caught:
            check_synced(self.clone, "feature", pr_head)
        return str(caught.exception)

    def replaced(self, pr_head):
        """The PR commits the clone last had that the PR head no longer has."""
        return git(self.clone, "rev-list", self.checked_out, "--not", pr_head).split()

    def assertNamesNoneOf(self, message, commits):
        for sha in re.findall(r"\b[0-9a-f]{7,40}\b", message):
            self.assertFalse(
                any(c.startswith(sha) for c in commits),
                f"names {sha}, which the clone got from the PR, as its own: {message}",
            )

    OWN: ClassVar = ["local only", "local only 2"]  # the clone's own commits, oldest first

    def own_local_commits(self):
        """The clone's own two commits, oldest first, in files no rewrite touches, so replaying
        them can't conflict."""
        commits = []
        for i, subject in enumerate(self.OWN):
            self.write(self.clone, f"mine{i}.py", "mine\n")
            git(self.clone, "add", f"mine{i}.py")
            git(self.clone, "commit", "-qm", subject)
            commits.append(git(self.clone, "rev-parse", "HEAD"))
        return commits

    def assertRebaseAdviceKeepsOnlyOwnWork(self, message, pr_head):
        """A rebase the message advises, run as written, puts only the clone's own commits on the
        PR head, in order, and leaves them the clone's own: unpushed work to push.

        `git rebase <pr head>` would replay the commits the rewrite replaced too (#7).
        """
        if not advises(message, "rebase"):
            return
        commands = re.findall(r"\bgit\s+rebase\b[^)`;,\n]*", message)
        self.assertTrue(commands, f"advises rebasing without the command to run: {message}")
        command = commands[0].rstrip(". ")
        out = subprocess.run(
            ["git", "-C", self.clone, *shlex.split(command)[1:]],
            capture_output=True,
            text=True,
            env=clean_env(),
            check=False,
        )
        self.assertEqual(out.returncode, 0, f"`{command}` fails: {out.stdout}{out.stderr}\n{message}")
        on_top = git(self.clone, "log", "--reverse", "--format=%s", f"{pr_head}..HEAD").splitlines()
        self.assertEqual(
            (on_top, git(self.clone, "rev-parse", f"HEAD~{len(self.OWN)}")),
            (self.OWN, pr_head),
            f"`{command}` doesn't leave just the clone's own commits on the PR head: {on_top}\n{message}",
        )
        # the rebased commits are still the clone's own, so the next step is to push them
        with self.assertRaises(Refusal, msg=f"after `{command}`") as caught:
            check_synced(self.clone, "feature", pr_head)
        self.assertIsInstance(caught.exception, NotPushed, f"after `{command}`: {caught.exception}")
        self.assertTrue(advises(str(caught.exception), "push"), str(caught.exception))

    def test_commits_a_rewrite_replaced_are_not_the_clones_own(self):
        """The clone got them from the PR, so a fetched rewrite means reset to it, not rebase."""
        for shape, ff, name, how in self.cases():
            with self.subTest(name, shape=shape, fast_forwarded=ff):
                self.start(shape, ff)
                self.rewrite(how)
                pr_head = self.fetch()
                message = self.refusal(pr_head)
                assert_moves_to_pr_head(self, message)
                self.assertNamesNoneOf(message, self.replaced(pr_head))

    def test_own_commits_alongside_a_rewrite_are_kept_and_the_replaced_ones_are_not(self):
        for shape, follow, (name, how) in [
            (shape, follow, rewrite) for shape in self.SHAPES for follow in self.FOLLOWS for rewrite in self.REWRITES
        ]:
            with self.subTest(name, shape=shape, follow=follow):
                self.start(shape, fast_forwarded=follow == "fast-forwarded, then committed")
                own = self.own_local_commits()
                if follow == "committed, then pulled with rebase":
                    own = self.follow_with_own_commits()
                elif follow == "committed, then pulled with pull.rebase=merges":
                    own = self.follow_with_own_commits("config")
                self.rewrite(how)
                pr_head = self.fetch()
                message = self.refusal(pr_head)
                named = re.findall(r"\b[0-9a-f]{7,40}\b", message)
                for local in own:
                    assert_keeps_local_work(self, message, local)
                    self.assertTrue(
                        any(local.startswith(sha) for sha in named),
                        f"doesn't name the clone's own commit {local[:12]}: {message}",
                    )
                # pushing the branch would put the replaced commits back on the PR
                self.assertFalse(advises(message, "push"), f"advises pushing: {message}")
                self.assertNamesNoneOf(message, self.replaced(pr_head))
                self.assertRebaseAdviceKeepsOnlyOwnWork(message, pr_head)

    # regression guards: both setups already get these right

    def test_own_commit_on_an_unchanged_pr_is_unpushed_work(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                self.start(shape)
                self.own_local_commits()
                with self.assertRaises(NotPushed) as caught:
                    check_synced(self.clone, "feature", self.fetch())
                self.assertTrue(advises(str(caught.exception), "push"), str(caught.exception))

    def test_own_commit_is_kept_when_the_pr_only_moved_on(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                self.start(shape)
                local = self.own_local_commits()[-1]
                self.commit(self.author, "three", "app.py", "line 25\n", "changed 25\n")
                self.publish()
                message = self.refusal(self.fetch())
                assert_keeps_local_work(self, message, local)
                self.assertNamesNoneOf(message, [self.one, self.reviewed])

    def test_clone_reset_to_the_rewritten_pr_head_is_accepted(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                self.start(shape)
                self.rewrite(RemoteSyncTest.amend_content)
                pr_head = self.fetch()
                git(self.clone, "reset", "-q", "--keep", pr_head)
                check_synced(self.clone, "feature", pr_head)


if __name__ == "__main__":
    unittest.main()
