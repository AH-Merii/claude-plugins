"""#9: comments are collected across separate commands and submitted as one review."""
import json
import unittest

from helpers import FakeGh, Repo, pr_table


class SubmitTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def gh(self, token="BOT_TOKEN"):
        return FakeGh(self.repo.path, pr_table(self.repo), token=token)

    def stage_two(self, gh):
        gh.run("--pr", "5", "comment", "app.py:10", "Why change this?")
        gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", input_text="x = 1\n")

    def review_posts(self, gh):
        return [c for c in gh.calls("/reviews") if c["stdin"].strip()]

    def test_staged_comments_go_out_together_in_one_request(self):
        gh = self.gh()
        self.stage_two(gh)
        self.assertEqual(self.review_posts(gh), [], "nothing is posted before submit")
        gh.run("--pr", "5", "submit", "changes", "Two things to fix.")
        (post,) = self.review_posts(gh)
        review = json.loads(post["stdin"])
        self.assertEqual(len(review["comments"]), 2)
        self.assertEqual(review["commit_id"], self.repo.head)

    def test_bot_verdicts_are_formal_review_states(self):
        for verdict, event in (("changes", "REQUEST_CHANGES"), ("pass", "APPROVE")):
            with self.subTest(verdict=verdict):
                gh = self.gh()
                gh.run("--pr", "5", "submit", verdict, "Summary.")
                (post,) = self.review_posts(gh)
                self.assertEqual(json.loads(post["stdin"])["event"], event)
                self.assertEqual(post["gh_token"], "BOT_TOKEN")

    def test_without_the_bot_the_review_is_a_comment_from_the_user(self):
        gh = self.gh(token=None)
        out = gh.run("--pr", "5", "submit", "changes", "Summary.")
        (post,) = self.review_posts(gh)
        review = json.loads(post["stdin"])
        self.assertEqual(review["event"], "COMMENT")
        self.assertIsNone(post["gh_token"])
        self.assertIn("changes", review["body"])
        self.assertIn("bot", out.stderr.lower(), "the fallback is explained, not silent")

    def test_failed_submit_keeps_the_staged_comments(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.set_answer("/reviews", exit=1)
        self.assertNotEqual(gh.run("--pr", "5", "submit", "changes", "S.", check=False).returncode, 0)
        gh.set_answer("/reviews", json.dumps({"html_url": "u"}))
        gh.run("--pr", "5", "submit", "changes", "S.")
        self.assertEqual(len(json.loads(self.review_posts(gh)[-1]["stdin"])["comments"]), 2)

    def test_successful_submit_starts_the_next_review_empty(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.run("--pr", "5", "submit", "changes", "S.")
        gh.run("--pr", "5", "submit", "pass", "All good.")
        self.assertEqual(json.loads(self.review_posts(gh)[-1]["stdin"]).get("comments", []), [])

    def test_line_outside_the_diff_is_refused_before_anything_is_staged(self):
        gh = self.gh()
        out = gh.run("--pr", "5", "comment", "app.py:1", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        gh.run("--pr", "5", "comment", "app.py:10", "This one is fine.")
        gh.run("--pr", "5", "submit", "changes", "S.")
        (sent,) = json.loads(self.review_posts(gh)[-1]["stdin"])["comments"]
        self.assertEqual(sent["line"], 10)


if __name__ == "__main__":
    unittest.main()
