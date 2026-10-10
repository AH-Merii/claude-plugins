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

from helpers import PLUGIN, numbered

REPO = os.environ.get("PR_THREADS_LIVE_REPO", "AH-Merii/test")
BOT = "ah-merii-claude-reviewer[bot]"


def sh(*args, cwd=None, input_text=None, env=None):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, input=input_text,
                         env={**os.environ, **(env or {})})
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


if __name__ == "__main__":
    unittest.main()
