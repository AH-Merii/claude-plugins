"""#9 writes suggested changes; #8 accepts them into the local file."""
import json
import os
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
        # a plain code fence ahead of a suggestion isn't mistaken for it
        self.assertEqual(parse_suggestion("```python\nprint(1)\n```\n\n```suggestion\nx = 1\n```\n"), "x = 1\n")


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


class AcceptByContentTest(unittest.TestCase):
    """accept finds its target by what the reviewer saw, not by the reviewed line numbers.

    Local edits elsewhere in the file shift line numbers, above or below, adding or removing
    lines; none of them is a reason to refuse. Only a change to the target lines themselves is.
    The reviewed head has `changed 10` at line 10 and `new a`, `new b` at lines 21-22.
    """

    # (name, edit to the reviewed file) applied before accepting
    SHIFTS = [
        ("one line added above", lambda t: "inserted\n" + t),
        ("three lines added above", lambda t: "a\nb\nc\n" + t),
        ("two lines removed above", lambda t: t.replace("line 1\nline 2\n", "")),
        ("one line split in two above", lambda t: t.replace("line 5\n", "line 5a\nline 5b\n")),
        ("lines added below", lambda t: t + "tail 1\ntail 2\n"),
        ("lines removed below", lambda t: t.replace("line 29\nline 30\n", "")),
        ("added above and removed below", lambda t: ("top\n" + t).replace("line 30\n", "")),
    ]
    # (start, end, what the reviewer saw there, replacement)
    TARGETS = [(10, 10, ["changed 10"], "fixed 10\n"), (21, 22, ["new a", "new b"], "x = 1\n")]

    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.pushed = self.repo.read("app.py")

    def accept(self, start, end, replacement):
        accept(self.repo.path, self.repo.head, "app.py", start, end, replacement)

    def expected(self, text, seen, replacement):
        """`text` with the block the reviewer saw replaced once, by content."""
        block = "".join(line + "\n" for line in seen)
        self.assertEqual(text.count(block), 1, "fixture: the reviewed block is unique")
        return text.replace(block, replacement)

    def test_local_edits_that_shift_lines_do_not_block_accept(self):
        for name, edit in self.SHIFTS:
            for start, end, seen, replacement in self.TARGETS:
                with self.subTest(edit=name, target=f"{start}-{end}"):
                    edited = edit(self.pushed)
                    self.repo.write("app.py", edited)
                    self.accept(start, end, replacement)
                    self.assertEqual(self.repo.read("app.py"), self.expected(edited, seen, replacement))

    def test_several_accepts_in_a_row_apply_in_either_order(self):
        # each accept changes the line count, so the next suggestion's lines have moved
        first, second = self.TARGETS
        for order in ((first, second), (second, first)):
            for grow in ("two\nlines\n", ""):
                with self.subTest(order=[f"{s}-{e}" for s, e, _, _ in order], replacement=grow):
                    self.repo.write("app.py", self.pushed)
                    want = self.pushed
                    for start, end, seen, _ in order:
                        self.accept(start, end, grow)
                        want = self.expected(want, seen, grow)
                    self.assertEqual(self.repo.read("app.py"), want)

    def test_a_change_to_the_target_itself_still_refuses_wherever_it_moved(self):
        changes = [
            ("rewritten in place", lambda t: t.replace("changed 10\n", "rewritten 10\n")
                                             .replace("new b\n", "newer b\n")),
            ("rewritten and moved down", lambda t: "inserted\n" + t.replace("changed 10\n", "rewritten 10\n")
                                                                   .replace("new b\n", "newer b\n")),
            ("rewritten and moved up", lambda t: t.replace("line 1\n", "").replace("changed 10\n", "rewritten 10\n")
                                                 .replace("new b\n", "newer b\n")),
            ("deleted", lambda t: t.replace("changed 10\n", "").replace("new a\nnew b\n", "")),
        ]
        for name, edit in changes:
            for start, end, _, replacement in self.TARGETS:
                with self.subTest(change=name, target=f"{start}-{end}"):
                    before = edit(self.pushed)
                    self.repo.write("app.py", before)
                    with self.assertRaises(StaleSuggestion):
                        self.accept(start, end, replacement)
                    self.assertEqual(self.repo.read("app.py"), before, "a refused accept leaves the file alone")


class AcceptLineEndingsTest(unittest.TestCase):
    """accept changes only the target lines: every other byte of the file stays as it was.

    Untouched lines keep their own endings (CRLF, LF or mixed), replacement lines take the
    file's CRLF where the file uses only CRLF, and a missing final newline stays missing.
    """

    def setUp(self):
        isolate_git(self)
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.files = 0

    def commit_bytes(self, name, data):
        with open(os.path.join(self.repo.path, name), "wb") as f:
            f.write(data)
        git(self.repo.path, "add", name)
        git(self.repo.path, "commit", "-qm", f"add {name}")
        return git(self.repo.path, "rev-parse", "HEAD")

    def accepted(self, data, start, end, replacement):
        """The bytes of a file holding `data` after accepting `replacement` for start..end."""
        self.files += 1
        name = f"f{self.files}.txt"  # a new file each time, so each case is its own commit
        commit = self.commit_bytes(name, data)
        accept(self.repo.path, commit, name, start, end, replacement)
        with open(os.path.join(self.repo.path, name), "rb") as f:
            return f.read()

    def test_untouched_lines_keep_their_bytes(self):
        cases = [
            ("crlf", b"one\r\ntwo\r\nthree\r\n", 2, 2, "TWO\n", b"one\r\nTWO\r\nthree\r\n"),
            ("crlf range", b"a\r\nb\r\nc\r\nd\r\n", 2, 3, "B\nC\nX\n", b"a\r\nB\r\nC\r\nX\r\nd\r\n"),
            ("crlf deletion", b"a\r\nb\r\nc\r\n", 2, 2, "", b"a\r\nc\r\n"),
            ("lf", b"one\ntwo\nthree\n", 2, 2, "TWO\n", b"one\nTWO\nthree\n"),
        ]
        for name, data, start, end, replacement, want in cases:
            with self.subTest(name):
                self.assertEqual(self.accepted(data, start, end, replacement), want)

    def test_mixed_endings_are_left_alone_outside_the_target(self):
        got = self.accepted(b"a\r\nb\nc\r\nd\n", 3, 3, "C\n")
        lines = got.splitlines(keepends=True)
        self.assertEqual((lines[0], lines[1], lines[3]), (b"a\r\n", b"b\n", b"d\n"))
        self.assertEqual(lines[2].rstrip(b"\r\n"), b"C")
        self.assertEqual(len(lines), 4)

    def test_a_missing_final_newline_stays_missing(self):
        # a suggestion's replacement always ends in a newline; the file's last line didn't
        for name, data, start, end, replacement, want in [
            ("last line replaced", b"one\ntwo\nthree", 3, 3, "THREE\n", b"one\ntwo\nTHREE"),
            ("range to the end", b"one\ntwo\nthree", 2, 3, "X\nY\nZ\n", b"one\nX\nY\nZ"),
            ("earlier line replaced", b"one\ntwo\nthree", 1, 1, "ONE\n", b"ONE\ntwo\nthree"),
            ("crlf, last line replaced", b"one\r\ntwo", 2, 2, "TWO\n", b"one\r\nTWO"),
        ]:
            with self.subTest(name):
                self.assertEqual(self.accepted(data, start, end, replacement), want)


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
    MULTI_LINE = "Name these.\n\n```suggestion\nx = 1\n```\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.reviewed = self.repo.head

    def accept_thread(self, body, line=10, start=None, outdated=False, before=()):
        """Accept T1, a thread made on the reviewed commit, with `body` as its comment.

        `before` are threads GitHub lists ahead of T1.
        """
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        gh.set_answer("graphql reviewThreads", json.dumps(response(
            *before,
            thread("T1", outdated=outdated, line=line, start=start, comments=(("bot", body),),
                   commit=self.reviewed))))
        return gh, gh.run("--pr", "5", "accept", "T1", check=False)

    def thread_reads(self, gh):
        return [c for c in gh.calls() if "reviewThreads" in json.dumps(c["body"])]

    def accept_outdated(self, body=SUGGESTION, line=10, start=None):
        """The author pushed after the review; the thread now only knows its original place."""
        git(self.repo.path, "commit", "-qam", "after the review")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        return self.accept_thread(body, line, start, outdated=True)

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
        gh, out = self.accept_outdated()
        self.assertNotEqual(out.returncode, 0)
        self.assertTrue(self.thread_reads(gh), "it read the thread before refusing")
        self.assertIn("rewritten 10", self.repo.read("app.py"))

    def assertRangeReplaced(self, out):
        """Lines 21-22 (`new a`, `new b`) became the one line `x = 1`."""
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = self.repo.read("app.py").splitlines()
        self.assertEqual(lines[20:22], ["x = 1", "line 21"])
        self.assertEqual(len(lines), 31)

    def test_multi_line_suggestion_replaces_its_whole_range(self):
        _, out = self.accept_thread(self.MULTI_LINE, line=22, start=21)
        self.assertRangeReplaced(out)

    def test_outdated_multi_line_suggestion_replaces_its_original_range(self):
        self.repo.write("app.py", self.repo.read("app.py").replace("line 28\n", "edited 28\n"))
        _, out = self.accept_outdated(self.MULTI_LINE, line=22, start=21)
        self.assertRangeReplaced(out)
        self.assertIn("edited 28", self.repo.read("app.py"))

    def test_finds_its_thread_past_the_first_page_of_threads(self):
        # GitHub serves at most 100 threads a page, so T1 is on page 2
        others = [thread(f"T{i}", resolved=True, commit=self.reviewed) for i in range(100, 200)]
        _, out = self.accept_thread(self.SUGGESTION, before=others)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.repo.read("app.py").splitlines()[9], "fixed 10")

    def test_thread_without_a_suggestion_is_refused(self):
        before = self.repo.read("app.py")
        gh, out = self.accept_thread("Looks wrong, see `foo`.")
        self.assertNotEqual(out.returncode, 0)
        self.assertTrue(self.thread_reads(gh), "it read the thread before refusing")
        self.assertIn("suggestion", out.stderr.lower(), "the refusal says why")
        self.assertEqual(self.repo.read("app.py"), before)


if __name__ == "__main__":
    unittest.main()
