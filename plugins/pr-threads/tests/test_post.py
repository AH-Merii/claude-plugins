"""post: a general comment on an issue or a PR conversation, sent with the user's own login."""
import json
import os
import unittest

from helpers import FakeGh, Repo, pr_table, write_png

POSTED = {"stdout": json.dumps({"html_url": "https://github.com/o/r/issues/7#issuecomment-1"})}


class PostTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def fake(self, table):
        # the bot is available, so a post that still goes out as the user proves the choice
        gh = FakeGh(self.repo.path, {**table, "POST /comments": POSTED}, token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        return gh

    def posts(self, gh):
        return [c for c in gh.calls() if c["method"] == "POST"]

    def test_posts_once_as_the_user_to_that_number(self):
        gh = self.fake({"repo view": pr_table(self.repo)["repo view"]})
        gh.run("post", "7", "Tracked in the follow-up.")
        (call,) = self.posts(gh)
        self.assertTrue(call["endpoint"].rstrip("/").endswith("repos/o/r/issues/7/comments"))
        self.assertIsNone(call["gh_token"], "the bot can't comment on plain issues")
        self.assertIn("Tracked in the follow-up.", call["body"]["body"])
        self.assertEqual(gh.calls("pr view"), [], "a plain issue needs no pull request lookup")

    def test_pr_number_posts_to_the_conversation_not_a_review(self):
        gh = self.fake(pr_table(self.repo))
        gh.run("post", "5", "General note on the PR.")
        (call,) = self.posts(gh)
        self.assertTrue(call["endpoint"].rstrip("/").endswith("repos/o/r/issues/5/comments"))
        self.assertEqual(gh.review_posts(), [])
        self.assertEqual(gh.calls("graphql"), [])

    def test_attachments_are_uploaded_as_the_user_and_kept_in_order(self):
        gh = self.fake({"repo view": pr_table(self.repo)["repo view"]})
        write_png(self.repo.path, "before.png", "after.png")
        gh.run("post", "7", "Repro below.", "--attach", "before.png", "--attach", "after.png#fixed")
        uploads = gh.upload_calls()
        self.assertEqual([os.path.basename(u["file"]) for u in uploads], ["before.png", "after.png"])
        self.assertTrue(all(u["gh_token"] is None for u in uploads))
        (call,) = self.posts(gh)
        body = call["body"]["body"]
        self.assertIn("Repro below.", body)
        self.assertLess(body.index("assets/before.png)"), body.index("![fixed](https://github.com/user-attachments/assets/after.png)"))

    def test_failed_upload_posts_nothing(self):
        gh = self.fake({"repo view": pr_table(self.repo)["repo view"]})
        write_png(self.repo.path, "after.png")
        gh.fail_uploads()
        out = gh.run("post", "7", "See image.", "--attach", "after.png", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(len(gh.upload_calls()), 1, "the upload was tried, and its failure stopped the post")
        self.assertEqual(self.posts(gh), [])

    def test_a_rejected_post_is_reported_as_a_failure(self):
        gh = self.fake({"repo view": pr_table(self.repo)["repo view"]})
        gh.set_answer("POST /comments", exit=1)
        out = gh.run("post", "7", "Will be refused.", check=False)
        self.assertEqual(len(self.posts(gh)), 1, "the post was sent, and GitHub refused it")
        self.assertNotEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
