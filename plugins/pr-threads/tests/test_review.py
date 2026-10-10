"""#9: comments are collected across separate commands and submitted as one review."""
import json
import unittest

from helpers import INSTALL_URL, FakeGh, Repo, git, pr_table


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

    def test_without_the_bot_the_review_is_a_comment_from_the_user(self):
        gh = self.gh(token=None)
        out = gh.run("--pr", "5", "submit", "changes", "Summary.")
        (review,) = gh.review_posts()
        self.assertEqual(review["event"], "COMMENT")
        (post,) = [c for c in gh.calls("POST") if c["body"] == review]
        self.assertIsNone(post["gh_token"])
        self.assertIn("changes", review["body"])
        self.assertIn("bot", out.stderr.lower(), "the fallback is explained, not silent")
        self.assertIn(INSTALL_URL, out.stderr, "and says how to set the bot up for this repo")

    # The user gives a verdict in chat and Claude records it on the PR as the user. GitHub
    # refuses APPROVE and REQUEST_CHANGES from a PR's author, so it is a comment review whose
    # first line is the keyword.
    def test_as_me_posts_one_comment_review_led_by_the_keyword(self):
        for verdict in ("pass", "changes"):
            with self.subTest(verdict=verdict):
                gh = self.gh()
                gh.run("--pr", "5", "submit", verdict, "--as-me")
                (review,) = gh.review_posts()
                self.assertEqual(review["event"], "COMMENT")
                self.assertEqual(review["body"].splitlines()[0], verdict)
                (post,) = gh.calls("POST")
                self.assertEqual(post["body"], review, "the review is the only thing posted")

    def test_as_me_keeps_the_users_words_after_the_keyword(self):
        gh = self.gh()
        gh.run("--pr", "5", "submit", "changes", "Rename this first.", "--as-me")
        (review,) = gh.review_posts()
        first, *rest = review["body"].splitlines()
        self.assertEqual(first, "changes")
        self.assertIn("Rename this first.", "\n".join(rest))

    def test_as_me_uses_the_users_login_and_never_mints_a_bot_token(self):
        for token in ("BOT_TOKEN", None):
            with self.subTest(bot_installed=bool(token)):
                gh = self.gh(token=token)
                out = gh.run("--pr", "5", "submit", "pass", "--as-me")
                (review,) = gh.review_posts()
                self.assertEqual(review["event"], "COMMENT")
                self.assertEqual({c["gh_token"] for c in gh.calls()}, {None},
                                 "no request carries GH_TOKEN or GITHUB_TOKEN")
                self.assertEqual(gh.token_mints(), 0, "the bot's token command never runs")
                self.assertNotIn(INSTALL_URL, out.stderr, "there is no fallback to explain")

    def test_as_me_leaves_the_bots_staged_comments_to_the_bot(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.run("--pr", "5", "submit", "pass", "--as-me")
        (mine,) = gh.review_posts()
        self.assertEqual(mine.get("comments", []), [], "the bot's comments don't go out under the user's login")
        gh.run("--pr", "5", "submit", "changes", "Two things to fix.")
        bots = gh.review_posts()[-1]
        self.assertEqual(bots["event"], "REQUEST_CHANGES")
        self.assertEqual(len(bots["comments"]), 2, "they stay staged for the bot, and --as-me staged none")

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

    def test_comments_are_refused_when_the_local_branch_is_not_the_pr_head(self):
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


if __name__ == "__main__":
    unittest.main()
