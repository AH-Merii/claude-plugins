"""#10: threads get resolved in bulk, and the handoff state reads straight off the PR."""
import json
import unittest

from helpers import FakeGh, Repo, pr_table
from test_threads import response, thread

from pr_threads.review import review_body
from pr_threads.status import handoff


def review(verdict, at, state="COMMENTED"):
    return {"state": state, "body": review_body(verdict, "summary"), "submitted_at": at}


class HandoffTest(unittest.TestCase):
    def assertHandoff(self, got, state, open_count):
        self.assertEqual((got["state"], got["open"]), (state, open_count))

    def test_no_review_yet_is_pending(self):
        self.assertHandoff(handoff(response(), []), "pending", 0)

    def test_pass_with_no_open_threads_is_a_pass(self):
        got = handoff(response(thread("T1", resolved=True)), [review("pass", "2026-10-10T10:00:00Z")])
        self.assertHandoff(got, "pass", 0)

    def test_open_threads_block_a_pass(self):
        got = handoff(response(thread("T1")), [review("pass", "2026-10-10T10:00:00Z")])
        self.assertHandoff(got, "changes", 1)

    def test_latest_verdict_wins(self):
        reviews = [review("changes", "2026-10-10T11:00:00Z"), review("pass", "2026-10-10T10:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "changes")
        reviews = [review("pass", "2026-10-10T12:00:00Z")] + reviews
        self.assertEqual(handoff(response(), reviews)["state"], "pass")

    def test_reviews_without_a_verdict_are_ignored(self):
        human = {"state": "COMMENTED", "body": "nice work", "submitted_at": "2026-10-10T12:00:00Z"}
        reviews = [human, review("pass", "2026-10-10T10:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "pass")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")

    def test_several_threads_resolve_in_one_request_as_the_bot(self):
        self.gh.run("--pr", "5", "resolve", "T1", "T2", "T3")
        (call,) = self.gh.calls("graphql")
        sent = json.dumps(call)
        for thread_id in ("T1", "T2", "T3"):
            self.assertIn(thread_id, sent)
        self.assertEqual(call["gh_token"], "BOT_TOKEN")


if __name__ == "__main__":
    unittest.main()
