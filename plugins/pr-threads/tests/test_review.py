"""#9: comments are collected across separate commands and submitted as one review."""
import json
import unittest

from helpers import INSTALL_URL, FakeGh, Repo, git, pr_table

from pr_threads.suggestions import parse_suggestion


class SubmitTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def gh(self, token="BOT_TOKEN"):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token=token)
        self.addCleanup(gh.cleanup)
        return gh

    def stage_two(self, gh):
        gh.run("--pr", "5", "comment", "app.py:10", "Why change this?")
        gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", input_text="x = 1\n")

    def test_staged_comments_go_out_together_in_one_request(self):
        gh = self.gh()
        self.stage_two(gh)
        self.assertEqual(gh.review_posts(), [], "nothing is posted before submit")
        gh.run("--pr", "5", "submit", "changes", "Two things to fix.")
        (review,) = gh.review_posts()
        self.assertEqual(len(review["comments"]), 2)
        self.assertEqual(review["commit_id"], self.repo.head)
        (suggestion,) = [c for c in review["comments"] if "```suggestion" in c["body"]]
        self.assertEqual((suggestion["path"], suggestion.get("start_line"), suggestion["line"]),
                         ("app.py", 21, 22), "the replacement covers both lines, not just the last")
        self.assertIn("```suggestion\nx = 1\n```", suggestion["body"])

    def test_bot_verdicts_are_formal_review_states(self):
        for verdict, event in (("changes", "REQUEST_CHANGES"), ("pass", "APPROVE")):
            with self.subTest(verdict=verdict):
                gh = self.gh()
                gh.run("--pr", "5", "submit", verdict, "Summary.")
                (review,) = gh.review_posts()
                self.assertEqual(review["event"], event)
                (post,) = [c for c in gh.calls("POST") if c["body"] == review]
                self.assertEqual(post["gh_token"], "BOT_TOKEN")

    def test_without_the_bot_nothing_is_submitted(self):
        # no fallback to the user's login: GitHub refuses the author's own verdict
        gh = self.gh(token=None)
        self.stage_two(gh)
        out = gh.run("--pr", "5", "submit", "changes", "Summary.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(gh.review_posts(), [], "nothing is posted")
        self.assertIn(INSTALL_URL, out.stderr, "it says how to set the bot up for this repo")

    def test_failed_submit_keeps_the_staged_comments(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.set_answer("POST /reviews", exit=1)
        self.assertNotEqual(gh.run("--pr", "5", "submit", "changes", "S.", check=False).returncode, 0)
        gh.set_answer("POST /reviews", json.dumps({"html_url": "u"}))
        gh.run("--pr", "5", "submit", "changes", "S.")
        self.assertEqual(len(gh.review_posts()[-1]["comments"]), 2)

    def test_successful_submit_starts_the_next_review_empty(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.run("--pr", "5", "submit", "changes", "S.")
        gh.run("--pr", "5", "submit", "pass", "All good.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [])

    def test_line_outside_the_diff_is_refused_before_anything_is_staged(self):
        gh = self.gh()
        out = gh.run("--pr", "5", "comment", "app.py:1", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        gh.run("--pr", "5", "comment", "app.py:10", "This one is fine.")
        gh.run("--pr", "5", "submit", "changes", "S.")
        (sent,) = gh.review_posts()[-1]["comments"]
        self.assertEqual(sent["line"], 10)

    def test_comments_are_refused_while_the_local_branch_has_unpushed_commits(self):
        # issue #7: line numbers only mean something against the pushed head
        gh = self.gh()
        self.repo.write("other.py", "local only\n")
        git(self.repo.path, "commit", "-qam", "not pushed yet")
        for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
            with self.subTest(command=args[0]):
                out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("push", out.stderr.lower())
        git(self.repo.path, "reset", "-q", "--hard", self.repo.head)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "refused comments were not staged")

    def test_comments_are_refused_while_the_local_branch_is_behind_the_pr_head(self):
        # someone pushed to the PR since this clone last pulled
        local = self.repo.head
        self.repo.write("other.py", "pushed from elsewhere\n")
        git(self.repo.path, "commit", "-qam", "pushed from elsewhere")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        gh = self.gh()
        git(self.repo.path, "reset", "-q", "--hard", local)
        for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
            with self.subTest(command=args[0]):
                out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("pull", out.stderr.lower(), "the fix is to pull, not to push")
        git(self.repo.path, "reset", "-q", "--hard", self.repo.head)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "refused comments were not staged")

    def test_diverged_branch_is_told_to_reset_to_the_pr_head_not_to_pull_and_push(self):
        # the author amended and force-pushed after this clone checked the PR out
        reviewed = self.repo.head
        git(self.repo.path, "commit", "-q", "--amend", "-m", "head, reworded")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        gh = self.gh()
        git(self.repo.path, "reset", "-q", "--hard", reviewed)
        for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
            with self.subTest(command=args[0]):
                out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                self.assertNotEqual(out.returncode, 0)
                lower = out.stderr.lower()
                self.assertNotRegex(lower, r"\bpull\b(?!\s+request)", "pulling merges the old commits back")
                self.assertNotRegex(lower, r"\bpush\b", "pushing undoes the author's rewrite")
                self.assertRegex(lower, r"\breset\b|\bcheck ?out\b", "says to move to the PR head")
        self.assertEqual(gh.review_posts(), [])

    def test_comments_are_refused_when_the_pr_head_was_never_fetched(self):
        self.repo.head = "0" * 40
        gh = self.gh()
        out = gh.run("--pr", "5", "comment", "app.py:10", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertRegex(out.stderr.lower(), r"\bfetch\b|\bpull\b")

    def test_comment_on_a_locally_edited_file_is_refused(self):
        gh = self.gh()
        pushed = self.repo.read("app.py")
        self.repo.write("app.py", "inserted\n" + pushed)
        out = gh.run("--pr", "5", "comment", "app.py:10", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("app.py", out.stderr)
        self.assertRegex(out.stderr.lower(), r"uncommitted|modified|local", "the refusal says why")
        self.repo.write("app.py", pushed)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "the refused comment was not staged")


class SuggestInputTest(unittest.TestCase):
    """suggest never posts a deletion by accident.

    An empty or blank replacement, from stdin or from --replacement, is refused unless
    --delete asks for the deletion. A bare `suggest a.py:3 "new code"` from a tool whose
    stdin is empty is the accident this prevents.
    """

    BLANK = ["", " \n", "\n\n", "\t\n"]

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def gh(self):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        return gh

    def submitted(self, gh):
        gh.run("--pr", "5", "submit", "changes", "S.")
        return gh.review_posts()[-1].get("comments", [])

    def test_blank_replacement_is_refused_and_nothing_is_staged(self):
        cases = [("stdin", (), text) for text in self.BLANK] + \
                [("--replacement", ("--replacement", text), "") for text in ("", "   ", "\n")]
        for source, extra, stdin in cases:
            with self.subTest(source=source, replacement=extra[1:] or stdin):
                gh = self.gh()
                out = gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", *extra,
                             check=False, input_text=stdin)
                self.assertNotEqual(out.returncode, 0, f"staged as a deletion: {out.stdout}")
                self.assertIn("--delete", out.stderr, "the refusal says how to ask for a deletion")
                self.assertEqual(self.submitted(gh), [], "nothing was staged")

    def test_deletion_is_staged_when_asked_for(self):
        gh = self.gh()
        gh.run("--pr", "5", "suggest", "app.py:21-22", "Drop these.", "--delete")
        (comment,) = self.submitted(gh)
        self.assertEqual(parse_suggestion(comment["body"]), "")
        self.assertEqual((comment.get("start_line"), comment["line"]), (21, 22))

    def test_replacement_can_come_from_an_argument(self):
        gh = self.gh()
        gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", "--replacement", "x = 1")
        (comment,) = self.submitted(gh)
        self.assertEqual(parse_suggestion(comment["body"]), "x = 1\n")


if __name__ == "__main__":
    unittest.main()
