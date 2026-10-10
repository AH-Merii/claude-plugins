"""#7: local path:line is pinned to a line GitHub accepts in the PR diff, or refused up front."""
import os
import unittest

from helpers import Repo, advises, assert_keeps_local_work, assert_moves_to_pr_head, git, isolate_git

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
    RENAMES = {
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
        for name, old in [("pure", "pure.txt"), ("tail", "tail.txt"), ("mid", "mid.txt"),
                          ("into", "into.txt"), ("out", "sub2/out.txt")]:
            self.repo.write(old, "".join(f"{name} {i}\n" for i in range(1, 41)))
        git(path, "add", ".")
        git(path, "commit", "-qm", "files to rename")
        self.base = git(path, "rev-parse", "HEAD")
        git(path, "checkout", "-q", "-B", "feature")
        os.mkdir(os.path.join(path, "sub"))
        for old, new in [("pure.txt", "pure2.txt"), ("tail.txt", "tail2.txt"), ("mid.txt", "mid2.txt"),
                         ("into.txt", "sub/into.txt"), ("sub2/out.txt", "out.txt")]:
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
                git(self.repo.path, "reset", "-q", "--hard",
                    local_commit if name == "both moved" else self.repo.head)
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
        keeps = lambda test, message: assert_keeps_local_work(test, message, local)  # noqa: E731
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


if __name__ == "__main__":
    unittest.main()
