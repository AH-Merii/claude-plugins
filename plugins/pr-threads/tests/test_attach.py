"""--attach: screenshots and GIFs go into the comment as images, uploaded as the user."""
import json
import os
import unittest

from helpers import FakeGh, Repo, git, pr_table, write_png

from pr_threads.suggestions import parse_suggestion


class AttachTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)
        write_png(self.repo.path, "before.png", "after.png")

    def submitted_comments(self):
        return self.gh.review_posts()[-1].get("comments", [])

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

    def test_suggestion_keeps_its_fence_intact_next_to_the_image(self):
        self.gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", "--attach", "after.png#renamed",
                    input_text="x = 1\n")
        self.gh.run("--pr", "5", "submit", "changes", "S.")
        (comment,) = self.submitted_comments()
        self.assertEqual(parse_suggestion(comment["body"]), "x = 1\n", "the image didn't break the suggestion")
        self.assertIn("![renamed](https://github.com/user-attachments/assets/after.png)", comment["body"])

    def test_review_summary_carries_its_image_posted_as_the_bot(self):
        self.gh.run("--pr", "5", "submit", "changes", "Footer overlaps.", "--attach", "after.png#overlap")
        (review,) = self.gh.review_posts()
        self.assertIn("Footer overlaps.", review["body"])
        self.assertIn("![overlap](https://github.com/user-attachments/assets/after.png)", review["body"])
        (upload,) = self.gh.upload_calls()
        self.assertIsNone(upload["gh_token"])
        (post,) = [c for c in self.gh.calls("POST") if c["body"] == review]
        self.assertEqual(post["gh_token"], "BOT_TOKEN")

    def test_reply_carries_its_image_and_is_not_sent_if_the_upload_fails(self):
        self.gh.run("--pr", "5", "reply", "T1", "Fixed, see after.", "--attach", "after.png")
        sent = [c for c in self.gh.calls() if "T1" in c["threads"]]
        self.assertTrue(any("user-attachments/assets/after.png" in json.dumps(c) for c in sent))
        self.gh.fail_uploads()
        before = len(self.gh.calls())
        out = self.gh.run("--pr", "5", "reply", "T1", "Again.", "--attach", "after.png", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(any("Again." in json.dumps(c) for c in self.gh.calls()[before:]))


class UploadLastTest(unittest.TestCase):
    """No image is uploaded unless its comment will be staged or sent.

    An uploaded asset can't be deleted, so every refusal comes before any upload.
    """

    def fresh(self):
        """A new repo and fake gh for one case."""
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)
        write_png(self.repo.path, "after.png")

    def move_pr_head(self):
        """Stage a comment, then let the PR head move on, with the local branch following it."""
        self.gh.run("--pr", "5", "comment", "app.py:10", "Staged first.")
        self.repo.write("other.py", "pushed after the review\n")
        git(self.repo.path, "commit", "-qam", "pushed after the review")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        self.gh.set_answer("pr view 5", pr_table(self.repo)["pr view 5"]["stdout"])

    def commit_locally(self):
        self.repo.write("other.py", "not pushed\n")
        git(self.repo.path, "commit", "-qam", "not pushed")

    def fall_behind(self):
        self.commit_locally()
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        self.gh.set_answer("pr view 5", pr_table(self.repo)["pr view 5"]["stdout"])
        git(self.repo.path, "reset", "-q", "--hard", "HEAD~1")

    def edit_locally(self):
        self.repo.write("app.py", "inserted\n" + self.repo.read("app.py"))

    def test_every_refusal_comes_before_any_upload(self):
        comment = ("comment", "app.py:10", "Look.")
        suggest = ("suggest", "app.py:10", "Look.")
        nothing = lambda: None  # noqa: E731
        for name, prepare, args, stdin in [
            ("comment after the PR head moved", self.move_pr_head, comment, ""),
            ("suggest after the PR head moved", self.move_pr_head, suggest, "x = 1\n"),
            ("submit after the PR head moved", self.move_pr_head, ("submit", "pass", "Fine."), ""),
            ("unpushed local commit", self.commit_locally, comment, ""),
            ("branch behind the PR head", self.fall_behind, comment, ""),
            ("uncommitted edit to the file", self.edit_locally, comment, ""),
            ("line outside the diff", nothing, ("comment", "app.py:1", "Look."), ""),
            ("blank suggestion", nothing, suggest, ""),
        ]:
            with self.subTest(name):
                self.fresh()
                prepare()
                out = self.gh.run("--pr", "5", *args, "--attach", "after.png#shot",
                                  check=False, input_text=stdin)
                self.assertEqual(self.gh.upload_calls(), [], f"uploaded, then: {out.stderr or out.stdout}")
                self.assertNotEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
