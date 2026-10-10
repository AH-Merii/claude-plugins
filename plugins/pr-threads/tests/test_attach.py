"""--attach: screenshots and GIFs go into the comment as images, uploaded as the user."""
import json
import os
import unittest

from helpers import FakeGh, Repo, pr_table


class AttachTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        for name in ("before.png", "after.png"):
            with open(os.path.join(self.repo.path, name), "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

    def submitted_comments(self):
        posts = [c for c in self.gh.calls("/reviews") if c["stdin"].strip()]
        return json.loads(posts[-1]["stdin"]).get("comments", [])

    def test_bot_comment_embeds_images_uploaded_by_the_user(self):
        self.gh.run("--pr", "5", "comment", "app.py:10", "Header wraps now.",
                    "--attach", "before.png", "--attach", "after.png")
        self.gh.run("--pr", "5", "submit", "changes", "See the screenshots.")
        uploads = self.gh.upload_calls()
        self.assertEqual([os.path.basename(u["file"]) for u in uploads], ["before.png", "after.png"])
        for upload in uploads:
            self.assertIsNone(upload["gh_token"], "uploads must use the user's login, not the bot's")
        (comment,) = self.submitted_comments()
        body = comment["body"]
        before = body.index("](https://github.com/user-attachments/assets/before.png)")
        after = body.index("](https://github.com/user-attachments/assets/after.png)")
        self.assertLess(before, after, "images keep the order they were given in")
        self.assertIn("Header wraps now.", body)

    def test_alt_text_is_what_an_agent_reads_instead_of_the_image(self):
        self.gh.run("--pr", "5", "comment", "app.py:10", "Look.", "--attach", "after.png#footer overlaps the status bar")
        self.gh.run("--pr", "5", "submit", "changes", "S.")
        (comment,) = self.submitted_comments()
        self.assertIn("![footer overlaps the status bar](https://github.com/user-attachments/assets/after.png)",
                      comment["body"])

    def test_missing_file_fails_before_anything_is_uploaded_or_staged(self):
        out = self.gh.run("--pr", "5", "comment", "app.py:10", "Look.", "--attach", "nope.png", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.gh.upload_calls(), [])
        self.gh.run("--pr", "5", "submit", "pass", "Fine.")
        self.assertEqual(self.submitted_comments(), [])

    def test_failed_upload_leaves_no_comment_without_its_image(self):
        self.gh.fail_uploads()
        out = self.gh.run("--pr", "5", "comment", "app.py:10", "Look.", "--attach", "after.png", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.gh.run("--pr", "5", "submit", "pass", "Fine.")
        self.assertEqual(self.submitted_comments(), [])

    def test_reply_carries_its_image_and_is_not_sent_if_the_upload_fails(self):
        self.gh.run("--pr", "5", "reply", "T1", "Fixed, see after.", "--attach", "after.png")
        sent = [c for c in self.gh.calls() if "T1" in json.dumps(c)]
        self.assertTrue(any("user-attachments/assets/after.png" in json.dumps(c) for c in sent))
        self.gh.fail_uploads()
        before = len(self.gh.calls())
        out = self.gh.run("--pr", "5", "reply", "T1", "Again.", "--attach", "after.png", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(any("Again." in json.dumps(c) for c in self.gh.calls()[before:]))


if __name__ == "__main__":
    unittest.main()
