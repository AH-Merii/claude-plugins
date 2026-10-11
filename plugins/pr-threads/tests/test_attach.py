"""--attach: screenshots and GIFs go into the comment as images, uploaded as the user."""

import json
import os
import re
import subprocess
import sys
import unittest

from helpers import (
    BOT_SLUG,
    INSTALL_URL,
    PLUGIN,
    FakeGh,
    Repo,
    bot_reply,
    clean_env,
    fake_with_threads,
    git,
    node,
    pr_table,
    write_png,
)

from pr_threads.suggestions import parse_suggestion

TEXT = "Footer overlaps the status bar."
POSTED = json.dumps({"html_url": "https://github.com/o/r/issues/5#issuecomment-1"})
# every verb that posts a body, reason or note -> arguments that make it post TEXT on PR 5
# ("HEAD" stands for the PR head)
TEXT_VERBS = {
    "comment": ("app.py:10", TEXT),
    "suggest": ("app.py:10", TEXT),
    "submit": ("changes", TEXT),
    "verify": ("T1", "HEAD", TEXT),
    "withdraw": ("T1", TEXT),
    "dispute": ("T1", TEXT),
    "reopen": ("T1", TEXT),
    "reply": ("T1", TEXT),
    "post": ("5", TEXT),
}
# the verbs that post no text of their own
OTHER_VERBS = {"discard", "resolve", "threads", "accept", "status"}


def strings(value):
    """Every string inside a recorded request."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


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
        self.gh.run(
            "--pr", "5", "comment", "app.py:10", "Header wraps now.", "--attach", "before.png", "--attach", "after.png"
        )
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
        self.gh.run(
            "--pr", "5", "comment", "app.py:10", "Look.", "--attach", "after.png#footer overlaps the status bar"
        )
        self.gh.run("--pr", "5", "submit", "changes", "S.")
        (comment,) = self.submitted_comments()
        self.assertIn(
            "![footer overlaps the status bar](https://github.com/user-attachments/assets/after.png)", comment["body"]
        )

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
        self.gh.run(
            "--pr", "5", "suggest", "app.py:21-22", "Name these.", "--attach", "after.png#renamed", input_text="x = 1\n"
        )
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


class EveryVerbAttachTest(unittest.TestCase):
    """Every verb that posts a body, reason or note takes `--attach FILE[#ALT]`, repeatable.

    Each image is uploaded with the user's login, then embedded in the posted text, in the
    order given, with ALT (or the file name) as its alt text. A missing file is refused
    before anything is uploaded or posted, and a failed upload posts nothing.
    """

    def fresh(self, token="BOT_TOKEN"):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = fake_with_threads(self.repo, token, node("T1", (BOT_SLUG, "Rename this.")))
        self.addCleanup(self.gh.cleanup)
        self.gh.set_answer("POST /comments", POSTED)
        write_png(self.repo.path, "before.png", "after.png")

    def run_verb(self, verb, *attach):
        args = [self.repo.head if a == "HEAD" else a for a in TEXT_VERBS[verb]]
        attach = [arg for item in attach for arg in ("--attach", item)]
        return self.gh.run("--pr", "5", verb, *args, *attach, check=False, input_text="x = 1\n")

    def test_every_verb_is_held_to_the_rule_or_known_to_post_no_text(self):
        """A verb added later fails here until it's listed in TEXT_VERBS or OTHER_VERBS."""
        out = subprocess.run(
            [sys.executable, "-m", "pr_threads", "--help"],
            capture_output=True,
            text=True,
            env=clean_env(PYTHONPATH=PLUGIN),
        )
        listed = re.search(r"\{([\w,-]+)\}", out.stdout)
        self.assertTrue(listed, f"no verb list in --help: {out.stdout}")
        verbs = set(listed[1].split(","))
        self.assertEqual(verbs - TEXT_VERBS.keys() - OTHER_VERBS, set(), "verbs nobody classified")
        self.assertEqual(TEXT_VERBS.keys() - verbs, set(), "text verbs pr-threads doesn't have")

    def test_every_verb_embeds_its_images_in_what_it_posts(self):
        before = "](https://github.com/user-attachments/assets/before.png)"
        after = "![the overlap](https://github.com/user-attachments/assets/after.png)"
        for verb in TEXT_VERBS:
            with self.subTest(verb):
                self.fresh()
                out = self.run_verb(verb, "before.png", "after.png#the overlap")
                self.assertEqual(out.returncode, 0, out.stderr)
                if not self.gh.writes():  # a staged comment goes out with the review
                    self.gh.run("--pr", "5", "submit", "changes", "See the comments.")
                posted = [s for s in strings(self.gh.writes()) if TEXT in s]
                self.assertTrue(posted, f"{verb} posted nothing with its text")
                self.assertTrue(
                    any(before in s and after in s and s.index(before) < s.index(after) for s in posted),
                    f"the images aren't in what {verb} posted, in order: {posted}",
                )
                uploads = self.gh.upload_calls()
                self.assertEqual([os.path.basename(u["file"]) for u in uploads], ["before.png", "after.png"])
                for upload in uploads:
                    self.assertIsNone(upload["gh_token"], "uploads use the user's login, not the bot's")

    def test_a_missing_file_is_refused_before_anything_is_uploaded_or_posted(self):
        for verb in TEXT_VERBS:
            with self.subTest(verb):
                self.fresh()
                out = self.run_verb(verb, "after.png", "nope.png")
                self.assertNotEqual(out.returncode, 0, f"{verb} went through: {out.stdout}")
                self.assertRegex(
                    out.stderr,
                    r"(?i)nope\.png\W.*no such file|no such file\W.*nope\.png",
                    "the refusal names the missing file",
                )
                self.assertEqual(self.gh.upload_calls(), [])
                self.assertEqual(self.gh.writes(), [])

    def test_a_failed_upload_posts_nothing(self):
        for verb in TEXT_VERBS:
            with self.subTest(verb):
                self.fresh()
                self.gh.fail_uploads()
                out = self.run_verb(verb, "after.png")
                self.assertNotEqual(out.returncode, 0, f"{verb} went through: {out.stdout}")
                self.assertRegex(out.stderr, r"(?i)upload", "the failure says the upload failed")
                self.assertTrue(self.gh.upload_calls(), "the upload was tried, and its failure stopped the post")
                self.assertEqual(self.gh.writes(), [])


class BotVerdictAttachTest(unittest.TestCase):
    """The bot's verdict replies keep their meaning with an image attached.

    status and resolve read a verify, withdraw, dispute or reopen reply carrying an image
    exactly as they read one without: only a dispute is disputed, and only a verification or
    withdrawal lets the thread resolve. Each follows an earlier bot verdict it must override,
    so a reply that lost its marker reads as that earlier verdict instead.
    """

    # verb -> (the bot's earlier verdict, disputed, resolves)
    VERDICTS = {
        "verify": ("dispute", False, True),
        "withdraw": ("dispute", False, True),
        "dispute": ("withdraw", True, False),
        "reopen": ("dispute", False, False),
    }

    def attached_reply(self, verb):
        """The body `verb` posts as the bot with an image attached."""
        repo = Repo()
        self.addCleanup(repo.cleanup)
        gh = fake_with_threads(repo, "BOT_TOKEN", node("T1", (BOT_SLUG, "Rename this.")))
        self.addCleanup(gh.cleanup)
        write_png(repo.path, "after.png")
        args = (repo.head,) if verb == "verify" else ("The cache was cold in #12.",)
        out = gh.run("--pr", "5", verb, "T1", *args, "--attach", "after.png#proof", check=False)
        self.assertEqual(out.returncode, 0, out.stderr)
        (reply,) = [r for call in gh.writes() for r in call["replies"]]
        self.assertIn("![proof](https://github.com/user-attachments/assets/after.png)", reply["body"])
        return reply["body"]

    def test_status_and_resolve_read_the_verdict_through_the_image(self):
        for verb, (earlier, disputed, resolves) in self.VERDICTS.items():
            with self.subTest(verb, after=earlier):
                body = self.attached_reply(verb)
                repo = Repo()
                self.addCleanup(repo.cleanup)
                thread = node(
                    "T1",
                    (BOT_SLUG, "Cache this."),
                    ("AH-Merii", "Fixed."),
                    (BOT_SLUG, bot_reply(earlier, "An earlier verdict.")),
                    (BOT_SLUG, body),
                    resolved=False,
                )
                gh = fake_with_threads(repo, "BOT_TOKEN", thread)
                self.addCleanup(gh.cleanup)
                got = json.loads(gh.run("--pr", "5", "status", "--json").stdout)
                self.assertEqual(got["disputed"], ["T1"] if disputed else [])
                out = gh.run("--pr", "5", "resolve", "T1", check=False)
                self.assertEqual(out.returncode == 0, resolves, out.stderr or out.stdout)


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
                out = self.gh.run("--pr", "5", *args, "--attach", "after.png#shot", check=False, input_text=stdin)
                self.assertEqual(self.gh.upload_calls(), [], f"uploaded, then: {out.stderr or out.stdout}")
                self.assertNotEqual(out.returncode, 0)

    def test_the_bots_refusals_come_before_any_upload(self):
        """Without the bot, with a blank reason, or verifying a commit outside the PR."""
        cases = [
            (f"{verb} without the bot", None, (verb, "T1", "The cache was cold."), INSTALL_URL)
            for verb in ("withdraw", "dispute", "reopen")
        ]
        cases += [
            (f"{verb} with a blank reason", "BOT_TOKEN", (verb, "T1", "  "), "(?i)reason")
            for verb in ("withdraw", "dispute", "reopen")
        ]
        cases += [
            ("submit without the bot", None, ("submit", "changes", "Fix it."), INSTALL_URL),
            ("verify without the bot", None, ("verify", "T1", "HEAD"), INSTALL_URL),
            ("verify a commit outside the PR", "BOT_TOKEN", ("verify", "T1", "0" * 40), "0000000"),
        ]
        for name, token, args, says in cases:
            with self.subTest(name):
                self.repo = Repo()
                self.addCleanup(self.repo.cleanup)
                self.gh = fake_with_threads(self.repo, token, node("T1", (BOT_SLUG, "Rename this.")))
                self.addCleanup(self.gh.cleanup)
                write_png(self.repo.path, "after.png")
                args = tuple(self.repo.head if a == "HEAD" else a for a in args)
                out = self.gh.run("--pr", "5", *args, "--attach", "after.png#shot", check=False)
                self.assertNotEqual(out.returncode, 0)
                self.assertRegex(
                    out.stderr, says if says.startswith("(?i)") else re.escape(says), "it refuses for its own reason"
                )
                self.assertEqual(self.gh.upload_calls(), [], f"uploaded, then: {out.stderr}")
                self.assertEqual(self.gh.writes(), [])


if __name__ == "__main__":
    unittest.main()
