"""#10: threads get resolved in bulk, and the handoff state reads straight off the PR."""
import json
import unittest

from helpers import FakeGh, Repo, pr_table, thread
from helpers import threads_response as response

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

    # GitHub lists reviews oldest first, so in every fixture the first review is the stale one
    def test_latest_verdict_wins(self):
        reviews = [review("pass", "2026-10-10T10:00:00Z"), review("changes", "2026-10-10T11:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "changes")
        reviews = reviews + [review("pass", "2026-10-10T12:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "pass")

    def test_reviews_without_a_verdict_are_ignored(self):
        human = {"state": "COMMENTED", "body": "nice work", "submitted_at": "2026-10-10T12:00:00Z"}
        reviews = [review("pass", "2026-10-10T10:00:00Z"), human]
        self.assertEqual(handoff(response(), reviews)["state"], "pass")


class HumanVerdictTest(unittest.TestCase):
    """The user's own review counts: the latest verdict wins, whoever gave it."""

    def human(self, state, at, body="Looks good."):
        return {"state": state, "body": body, "submitted_at": at}

    def test_approval_with_no_open_threads_is_a_pass(self):
        got = handoff(response(thread("T1", resolved=True)), [self.human("APPROVED", "2026-10-10T10:00:00Z")])
        self.assertEqual((got["state"], got["open"]), ("pass", 0))

    def test_approval_after_a_bot_change_request_is_a_pass(self):
        reviews = [review("changes", "2026-10-10T10:00:00Z"), self.human("APPROVED", "2026-10-10T11:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "pass")

    def test_a_later_bot_change_request_overrides_an_older_approval(self):
        reviews = [self.human("APPROVED", "2026-10-10T10:00:00Z"), review("changes", "2026-10-10T11:00:00Z")]
        self.assertEqual(handoff(response(), reviews)["state"], "changes")

    def test_approval_does_not_close_open_threads(self):
        got = handoff(response(thread("T1"), thread("T2")), [self.human("APPROVED", "2026-10-10T10:00:00Z")])
        self.assertEqual((got["state"], got["open"]), ("approved", 2))

    def test_change_request_blocks_even_after_a_bot_pass(self):
        reviews = [review("pass", "2026-10-10T10:00:00Z"),
                   self.human("CHANGES_REQUESTED", "2026-10-10T11:00:00Z", "Rename this first.")]
        self.assertEqual(handoff(response(), reviews)["state"], "changes")


class VerdictRoundTripTest(unittest.TestCase):
    """What submit writes is what handoff reads, as the bot and in the fallback."""

    STATES = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED", "COMMENT": "COMMENTED"}

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def posted_review(self, verdict, token):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token=token)
        self.addCleanup(gh.cleanup)
        gh.run("--pr", "5", "submit", verdict, "Summary.")
        (sent,) = gh.review_posts()
        # GitHub stores the event as a review state
        return {"state": self.STATES[sent["event"]], "body": sent.get("body", ""),
                "submitted_at": "2026-10-10T10:00:00Z"}

    def test_each_verdict_reads_back_the_same(self):
        for token in ("BOT_TOKEN", None):
            for verdict in ("pass", "changes"):
                with self.subTest(verdict=verdict, bot=bool(token)):
                    got = handoff(response(), [self.posted_review(verdict, token)])
                    self.assertEqual(got["state"], verdict)

    def test_bot_change_request_holds_even_with_no_open_threads(self):
        got = handoff(response(), [review("changes", "2026-10-10T10:00:00Z", state="CHANGES_REQUESTED")])
        self.assertEqual(got["state"], "changes")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)

    def test_several_threads_resolve_in_one_request_as_the_bot(self):
        self.gh.run("--pr", "5", "resolve", "T1", "T2", "T3")
        (call,) = self.gh.calls("graphql")
        self.assertEqual(call["fields"], ["resolveReviewThread"] * 3)
        sent = json.dumps(call)
        for thread_id in ("T1", "T2", "T3"):
            self.assertIn(thread_id, sent)
        self.assertEqual(call["gh_token"], "BOT_TOKEN")


class StatusCliTest(unittest.TestCase):
    """`status` reads the PR's reviews and threads and reports the handoff."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)

    def status(self, reviews, *threads):
        self.gh.set_answer("GET /reviews", json.dumps(reviews))
        self.gh.set_answer("graphql reviewThreads", json.dumps(response(*threads)))
        return self.gh.run("--pr", "5", "status").stdout.lower()

    def test_reports_the_latest_verdict_from_the_pr(self):
        out = self.status([review("pass", "2026-10-10T10:00:00Z", state="APPROVED"),
                           {"state": "CHANGES_REQUESTED", "body": "Rename first.",
                            "submitted_at": "2026-10-10T11:00:00Z"}],
                          thread("T1", resolved=True))
        self.assertIn("changes", out)
        self.assertNotRegex(out, r"\bpass\b")

    def test_reports_how_many_threads_are_still_open(self):
        out = self.status([{"state": "APPROVED", "body": "", "submitted_at": "2026-10-10T10:00:00Z"}],
                          thread("T1"), thread("T2"), thread("T3", resolved=True))
        self.assertIn("approved", out)
        self.assertRegex(out, r"\b2\b")
        self.assertNotRegex(out, r"\b3\b", "resolved threads aren't counted")


if __name__ == "__main__":
    unittest.main()
