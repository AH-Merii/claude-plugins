"""#9 writes suggested changes; #8 accepts them into the local file."""
import unittest

from helpers import Repo

from pr_threads.suggestions import StaleSuggestion, accept, parse_suggestion, suggestion_body


class RoundTripTest(unittest.TestCase):
    """Whatever the reviewer suggests is exactly what the author gets back."""

    def test_replacements_survive_the_comment_body(self):
        for replacement in ["x = 1\n", "a\nb\nc\n", "", "```python\ncode\n```\n"]:
            with self.subTest(replacement=replacement):
                body = suggestion_body("Use this instead.", replacement)
                self.assertEqual(parse_suggestion(body), replacement)

    def test_comment_without_a_suggestion_has_none(self):
        self.assertIsNone(parse_suggestion("Looks wrong, see `foo`."))
        self.assertIsNone(parse_suggestion("```python\nprint(1)\n```"))


class AcceptTest(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
