"""Contract with the real GitHub: one full review round on a throwaway PR.

Local only: needs the user's `gh` login, the reviewer bot installed on AH-Merii/test, and
network. Run with PR_THREADS_LIVE=1. The PR is closed and its branch deleted afterwards.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from helpers import BOT, GIT_REPO_VARS, PLUGIN, numbered

REPO = os.environ.get("PR_THREADS_LIVE_REPO", "AH-Merii/test")


def sh(*args, cwd=None, input_text=None, env=None):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, input=input_text,
                         env={**{k: v for k, v in os.environ.items() if k not in GIT_REPO_VARS},
                              **(env or {})})
    if out.returncode:
        raise AssertionError(f"{args} failed: {out.stderr}")
    return out.stdout.strip()


@unittest.skipUnless(os.environ.get("PR_THREADS_LIVE") == "1", "set PR_THREADS_LIVE=1 to run")
class LiveRoundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "clone")
        self.branch = f"pr-threads-live-{int(time.time())}"
        sh("gh", "repo", "clone", REPO, self.dir, "--", "-q")
        sh("git", "checkout", "-qb", self.branch, cwd=self.dir)
        with open(os.path.join(self.dir, "live.txt"), "w") as f:
            f.write(numbered(10))
        sh("git", "add", "live.txt", cwd=self.dir)
        # Throwaway commit on a PR that is never merged, so it skips the signing prompt
        sh("git", "-c", "commit.gpgsign=false", "commit", "-qm", "live test", cwd=self.dir)
        sh("git", "push", "-q", "origin", self.branch, cwd=self.dir)
        self.addCleanup(sh, "git", "push", "-q", "origin", "--delete", self.branch, cwd=self.dir)
        url = sh("gh", "pr", "create", "-R", REPO, "--head", self.branch,
                 "--title", "test: pr-threads live round", "--body", "Throwaway, closed by the test.")
        self.pr = url.rsplit("/", 1)[1]
        self.addCleanup(sh, "gh", "pr", "close", self.pr, "-R", REPO)

    def cli(self, *args, input_text=""):
        return sh(sys.executable, "-m", "pr_threads", "--pr", self.pr, *args, cwd=self.dir,
                  input_text=input_text, env={"PYTHONPATH": PLUGIN})

    def reviews(self):
        return json.loads(sh("gh", "api", f"repos/{REPO}/pulls/{self.pr}/reviews"))

    def test_full_round(self):
        self.cli("comment", "live.txt:3", "Why three?")
        self.cli("suggest", "live.txt:5-6", "Merge these.", input_text="line 5 and 6\n")
        self.cli("submit", "changes", "Two points.")

        (first,) = self.reviews()
        self.assertEqual((first["user"]["login"], first["state"]), (BOT, "CHANGES_REQUESTED"))

        threads = json.loads(self.cli("threads", "--json"))
        self.assertEqual(sorted((t["path"], t["line"]) for t in threads),
                         [("live.txt", 3), ("live.txt", 6)])
        by_line = {t["line"]: t["id"] for t in threads}

        self.cli("reply", by_line[3], "Because of the spec.")
        self.cli("accept", by_line[6])
        with open(os.path.join(self.dir, "live.txt")) as f:
            self.assertEqual(f.read().splitlines()[3:6], ["line 4", "line 5 and 6", "line 7"])

        self.cli("resolve", by_line[3], by_line[6])
        self.assertEqual(json.loads(self.cli("threads", "--json")), [])
        self.cli("submit", "pass", "Resolved.")
        status = json.loads(self.cli("status", "--json"))
        self.assertEqual((status["state"], status["open"]), ("pass", 0))
        self.assertEqual(self.reviews()[-1]["state"], "APPROVED")

    def test_attached_image_renders_inside_an_inline_comment(self):
        image = os.path.join(self.dir, "proof.png")
        with open(image, "wb") as f:
            f.write(tiny_png())
        self.cli("comment", "live.txt:3", "See proof.", "--attach", "proof.png#a red pixel")
        self.cli("submit", "changes", "One point.")
        (comment,) = json.loads(sh("gh", "api", "-H", "Accept: application/vnd.github.full+json",
                                   f"repos/{REPO}/pulls/{self.pr}/comments"))
        self.assertEqual(comment["user"]["login"], BOT)
        self.assertIn("user-attachments", comment["body"])
        self.assertIn("<img", comment["body_html"], "GitHub rendered it as an image, not a link")

    def test_post_comments_on_the_conversation_as_the_user(self):
        # post goes through gh issue comment, whose --attach uploads the image itself
        with open(os.path.join(self.dir, "proof.png"), "wb") as f:
            f.write(tiny_png())
        sh(sys.executable, "-m", "pr_threads", "post", self.pr, "Plain note.", cwd=self.dir,
           env={"PYTHONPATH": PLUGIN})
        sh(sys.executable, "-m", "pr_threads", "post", self.pr, "With proof.", "--attach",
           "proof.png#a red pixel", cwd=self.dir, env={"PYTHONPATH": PLUGIN})
        me = sh("gh", "api", "user", "--jq", ".login")
        plain, attached = json.loads(sh("gh", "api", "-H", "Accept: application/vnd.github.full+json",
                                        f"repos/{REPO}/issues/{self.pr}/comments"))
        self.assertEqual([plain["user"]["login"], attached["user"]["login"]], [me, me])
        self.assertIn("Plain note.", plain["body"])
        self.assertIn("With proof.", attached["body"])
        self.assertIn("user-attachments", attached["body"])
        self.assertIn("<img", attached["body_html"], "GitHub rendered it as an image, not a link")


def tiny_png():
    """A valid 1x1 red PNG, built with the standard library."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


if __name__ == "__main__":
    unittest.main()
