"""#8: the author sees only open threads, located by local path:line."""

import json
import unittest

from helpers import FakeGh, Repo, pr_table, thread
from helpers import threads_response as response

from pr_threads.threads import open_threads


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
        self.assertEqual([(c["author"], c["body"]) for c in got["comments"]], [("bot", "why?"), ("me", "because")])


class AuthorCliTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)

    def test_threads_are_read_and_replied_to_as_the_user(self):
        self.gh.set_answer("graphql reviewThreads", json.dumps(response(thread("T1"))))
        out = self.gh.run("--pr", "5", "threads")
        self.assertIn("app.py:10", out.stdout)
        before = len(self.gh.calls())
        self.gh.run("--pr", "5", "reply", "T1", "fixed in abc123")
        writes = {
            "addPullRequestReviewThreadReply",
            "resolveReviewThread",
            "unresolveReviewThread",
            "addPullRequestReview",
            "addPullRequestReviewComment",
        }
        (reply,) = [c for c in self.gh.calls()[before:] if writes & set(c["fields"])]
        self.assertEqual(reply["fields"], ["addPullRequestReviewThreadReply"])
        self.assertEqual(reply["threads"], ["T1"])
        self.assertIn("fixed in abc123", json.dumps(reply["body"]))
        for call in self.gh.calls():
            self.assertIsNone(call["gh_token"], "author commands must not post as the bot")

    def test_json_lists_each_open_thread_with_its_range_and_conversation(self):
        self.gh.set_answer(
            "graphql reviewThreads",
            json.dumps(
                response(
                    thread("T1", line=22, start=21, comments=(("bot", "why?"), ("me", "because"))),
                    thread("T2", outdated=True, line=12),
                    thread("T3", resolved=True),
                )
            ),
        )
        got = json.loads(self.gh.run("--pr", "5", "threads", "--json").stdout)
        self.assertEqual([t["id"] for t in got], ["T1", "T2"])
        current, outdated = got
        self.assertEqual(
            {k: current[k] for k in ("path", "line", "start_line", "outdated")},
            {"path": "app.py", "line": 22, "start_line": 21, "outdated": False},
        )
        self.assertEqual([(c["author"], c["body"]) for c in current["comments"]], [("bot", "why?"), ("me", "because")])
        self.assertEqual(
            {k: outdated[k] for k in ("path", "line", "start_line", "outdated")},
            {"path": "app.py", "line": 12, "start_line": None, "outdated": True},
        )

    def test_open_thread_past_the_first_page_is_listed(self):
        # GitHub serves at most 100 threads a page, so T100 is on page 2
        settled = [thread(f"T{i}", resolved=True) for i in range(100)]
        self.gh.set_answer("graphql reviewThreads", json.dumps(response(*settled, thread("T100"))))
        got = json.loads(self.gh.run("--pr", "5", "threads", "--json").stdout)
        self.assertEqual([t["id"] for t in got], ["T100"])

    def test_outdated_threads_are_flagged_in_the_output(self):
        self.gh.set_answer("graphql reviewThreads", json.dumps(response(thread("T1", outdated=True, line=12))))
        out = self.gh.run("--pr", "5", "threads").stdout
        self.assertIn("app.py:12", out)
        self.assertIn("outdated", out.lower())

    def test_resolved_threads_never_reach_the_output(self):
        self.gh.set_answer(
            "graphql reviewThreads",
            json.dumps(
                response(
                    thread("T1", comments=(("bot", "still open"),)),
                    thread("T2", resolved=True, comments=(("bot", "settled long ago"),)),
                )
            ),
        )
        out = self.gh.run("--pr", "5", "threads").stdout
        self.assertIn("still open", out)
        self.assertNotIn("settled long ago", out)


if __name__ == "__main__":
    unittest.main()
