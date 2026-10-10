"""#9 writes suggested changes; #8 accepts them into the local file."""
import json
import unittest

from helpers import FakeGh, Repo, git, isolate_git, pr_table, thread
from helpers import threads_response as response

from pr_threads.suggestions import StaleSuggestion, accept, parse_suggestion, suggestion_body


class RoundTripTest(unittest.TestCase):
    """Whatever the reviewer suggests is exactly what the author gets back."""

    def test_replacements_survive_the_comment_body(self):
        for replacement in ["x = 1\n", "a\nb\nc\n", "", "```python\ncode\n```\n"]:
            with self.subTest(replacement=replacement):
                body = suggestion_body("Use this instead.", replacement)
                self.assertEqual(parse_suggestion(body), replacement)

    def test_body_written_on_github_is_read(self):
        # GitHub's own syntax, as the web UI stores it: a ```suggestion fence, CRLF line ends
        for body in ["Name these.\n\n```suggestion\nx = 1\n```\n",
                     "Name these.\r\n\r\n```suggestion\r\nx = 1\r\n```"]:
            with self.subTest(body=body):
                self.assertEqual(parse_suggestion(body), "x = 1\n")

    def test_written_body_uses_githubs_suggestion_fence(self):
        self.assertIn("```suggestion\nx = 1\n```", suggestion_body("Name these.", "x = 1\n"))

    def test_comment_without_a_suggestion_has_none(self):
        self.assertIsNone(parse_suggestion("Looks wrong, see `foo`."))
        self.assertIsNone(parse_suggestion("```python\nprint(1)\n```"))


class AcceptTest(unittest.TestCase):
    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def accept(self, start, end, replacement):
        accept(self.repo.path, self.repo.head, "app.py", start, end, replacement)
        return self.repo.read("app.py").splitlines()

    def test_single_line_is_replaced(self):
        lines = self.accept(10, 10, "fixed 10\n")
        self.assertEqual(lines[8:11], ["line 9", "fixed 10", "line 11"])
        self.assertEqual(len(lines), 32)

    def test_range_is_replaced_by_more_lines(self):
        lines = self.accept(21, 22, "one\ntwo\nthree\n")
        self.assertEqual(lines[19:24], ["line 20", "one", "two", "three", "line 21"])
        self.assertEqual(len(lines), 33)

    def test_empty_replacement_deletes_the_range(self):
        lines = self.accept(21, 22, "")
        self.assertEqual(lines[19:21], ["line 20", "line 21"])
        self.assertEqual(len(lines), 30)

    def test_unrelated_local_edit_further_down_is_kept(self):
        self.repo.write("app.py", self.repo.read("app.py") + "local tail\n")
        lines = self.accept(10, 10, "fixed 10\n")
        self.assertEqual(lines[9], "fixed 10")
        self.assertEqual(lines[-1], "local tail")

    def test_target_lines_moved_since_the_review_are_refused(self):
        before = "inserted\n" + self.repo.read("app.py")
        self.repo.write("app.py", before)
        with self.assertRaises(StaleSuggestion):
            accept(self.repo.path, self.repo.head, "app.py", 10, 10, "fixed 10\n")
        self.assertEqual(self.repo.read("app.py"), before)


class OutdatedAcceptTest(unittest.TestCase):
    """An outdated thread points at originalLine in the commit it was written on."""

    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.reviewed = self.repo.head

    def commit_change(self, old, new):
        self.repo.write("app.py", self.repo.read("app.py").replace(old, new))
        git(self.repo.path, "commit", "-qam", "after the review")

    def test_target_rewritten_by_a_later_commit_is_refused(self):
        self.commit_change("changed 10\n", "rewritten 10\n")
        before = self.repo.read("app.py")
        with self.assertRaises(StaleSuggestion):
            accept(self.repo.path, self.reviewed, "app.py", 10, 10, "fixed 10\n")
        self.assertEqual(self.repo.read("app.py"), before)

    def test_later_commit_elsewhere_still_applies_at_the_reviewed_lines(self):
        self.commit_change("line 28\n", "edited 28\n")
        accept(self.repo.path, self.reviewed, "app.py", 10, 10, "fixed 10\n")
        lines = self.repo.read("app.py").splitlines()
        self.assertEqual((lines[9], lines[29]), ("fixed 10", "edited 28"))


class AcceptCliTest(unittest.TestCase):
    """`accept <thread>` finds the suggestion and where it was made from the thread itself."""

    SUGGESTION = "Clearer name.\n\n```suggestion\nfixed 10\n```\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.reviewed = self.repo.head

    def accept_outdated(self):
        """The author pushed after the review; the thread now only knows its original place."""
        git(self.repo.path, "commit", "-qam", "after the review")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        gh.set_answer("graphql reviewThreads", json.dumps(response(
            thread("T1", outdated=True, line=10, comments=(("bot", self.SUGGESTION),), commit=self.reviewed))))
        return gh, gh.run("--pr", "5", "accept", "T1", check=False)

    def test_applies_at_the_original_line_of_the_reviewed_commit(self):
        self.repo.write("app.py", self.repo.read("app.py").replace("line 28\n", "edited 28\n"))
        gh, out = self.accept_outdated()
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = self.repo.read("app.py").splitlines()
        self.assertEqual((lines[9], lines[29]), ("fixed 10", "edited 28"))
        self.assertEqual([c for c in gh.calls() if c["method"] == "POST" and c["endpoint"] != "graphql"], [])

    def test_lines_rewritten_since_the_reviewed_commit_are_refused(self):
        # against the current head these lines look untouched; only the reviewed commit shows the clash
        self.repo.write("app.py", self.repo.read("app.py").replace("changed 10\n", "rewritten 10\n"))
        _, out = self.accept_outdated()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("rewritten 10", self.repo.read("app.py"))


if __name__ == "__main__":
    unittest.main()
