"""#8: the author sees only open threads, located by local path:line."""
import json
import unittest

from helpers import FakeGh, Repo, pr_table

from pr_threads.threads import open_threads


def thread(id, resolved=False, outdated=False, line=10, start=None, comments=(("bot", "hi"),)):
    return {"id": id, "isResolved": resolved, "isOutdated": outdated, "path": "app.py",
            "line": None if outdated else line, "startLine": None if outdated else start,
            "originalLine": line, "originalStartLine": start,
            "comments": {"nodes": [{"author": {"login": a}, "body": b} for a, b in comments]}}


def response(*threads):
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": list(threads)}}}}}


class OpenThreadsTest(unittest.TestCase):
    def test_resolved_threads_are_left_out(self):
        got = open_threads(response(thread("T1"), thread("T2", resolved=True), thread("T3")))
        self.assertEqual([t["id"] for t in got], ["T1", "T3"])

    def test_outdated_thread_keeps_where_it_was(self):
        (got,) = open_threads(response(thread("T1", outdated=True, line=12)))
        self.assertTrue(got["outdated"])
        self.assertEqual((got["path"], got["line"]), ("app.py", 12))

    def test_multi_line_thread_keeps_its_range(self):
        (got,) = open_threads(response(thread("T1", line=22, start=21)))
        self.assertEqual((got["start_line"], got["line"]), (21, 22))

    def test_conversation_is_kept_in_order(self):
        (got,) = open_threads(response(thread("T1", comments=(("bot", "why?"), ("me", "because")))))
        self.assertEqual([(c["author"], c["body"]) for c in got["comments"]],
                         [("bot", "why?"), ("me", "because")])


class AuthorCliTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")

    def test_threads_are_read_and_replied_to_as_the_user(self):
        self.gh.set_answer("graphql", json.dumps(response(thread("T1"))))
        out = self.gh.run("--pr", "5", "threads")
        self.assertIn("app.py:10", out.stdout)
        before = len(self.gh.calls())
        self.gh.run("--pr", "5", "reply", "T1", "fixed in abc123")
        reply_calls = self.gh.calls()[before:]
        self.assertTrue(any("T1" in json.dumps(c) for c in reply_calls), "the reply was sent")
        for call in self.gh.calls():
            self.assertIsNone(call["gh_token"], "author commands must not post as the bot")

    def test_resolved_threads_never_reach_the_output(self):
        self.gh.set_answer("graphql", json.dumps(response(
            thread("T1", comments=(("bot", "still open"),)),
            thread("T2", resolved=True, comments=(("bot", "settled long ago"),)))))
        out = self.gh.run("--pr", "5", "threads").stdout
        self.assertIn("still open", out)
        self.assertNotIn("settled long ago", out)


if __name__ == "__main__":
    unittest.main()
