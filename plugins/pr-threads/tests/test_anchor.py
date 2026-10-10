"""#7: local path:line is pinned to a line GitHub accepts in the PR diff, or refused up front."""
import unittest

from helpers import Repo, git, isolate_git

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


class SyncTest(unittest.TestCase):
    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def test_branch_at_the_pr_head_is_accepted(self):
        check_synced(self.repo.path, "feature", self.repo.head)

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

    def test_pr_head_missing_locally_is_refused(self):
        with self.assertRaises(NotPulled) as caught:
            check_synced(self.repo.path, "feature", "0" * 40)
        self.assertNotIsInstance(caught.exception, NotPushed)
        self.assertRegex(str(caught.exception).lower(), r"\bfetch\b|\bpull\b")


if __name__ == "__main__":
    unittest.main()
