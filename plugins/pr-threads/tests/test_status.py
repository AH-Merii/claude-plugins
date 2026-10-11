"""#10: the handoff state reads straight off the PR. Resolving threads: test_resolve.py."""

import json
import unittest

from helpers import BOT, FakeGh, Repo, pages, pr_table, resolved_response, thread
from helpers import threads_response as response

from pr_threads.status import handoff


HUMAN = "octocat"


def at(hour):
    return f"2026-10-10T{hour:02d}:00:00Z"


def by(login, state, hour, body="", kind="User"):
    """A submitted review as GitHub's REST API lists it."""
    return {"user": {"login": login, "type": kind}, "state": state, "body": body, "submitted_at": at(hour)}


def bot(state, hour):
    """The bot's review: formal states, since the bot never authors the PR."""
    return by(BOT, state, hour, "Summary.", kind="Bot")


def human(state, hour, body="Looks good."):
    """A human reviewer who isn't the PR's author."""
    return by(HUMAN, state, hour, body)


def pending(login):
    """A draft review: GitHub shows it only to its author, with no submitted_at."""
    return {"user": {"login": login, "type": "User"}, "state": "PENDING", "body": "Rename this."}


class HandoffCase(unittest.TestCase):
    def assertHandoff(self, reviews, state, open_count=0, *threads):
        got = handoff(response(*threads), reviews)
        self.assertEqual((got["state"], got["open"]), (state, open_count))


class HandoffTest(HandoffCase):
    """The handoff reads formal review states, as GitHub does.

    A pass needs an approval, no outstanding change request and no open threads. An
    approval with threads still open reports `approved` and the open count, never a pass.
    COMMENTED reviews carry no verdict; DISMISSED and PENDING ones don't count.
    """

    def test_no_review_yet_is_pending(self):
        self.assertHandoff([], "pending")

    def test_approval_with_no_open_threads_is_a_pass(self):
        self.assertHandoff([bot("APPROVED", 10)], "pass", 0, thread("T1", resolved=True))

    def test_approval_with_open_threads_is_approved_not_a_pass(self):
        self.assertHandoff([bot("APPROVED", 10)], "approved", 1, thread("T1"), thread("T2", resolved=True))
        self.assertHandoff([human("APPROVED", 10)], "approved", 2, thread("T1"), thread("T2"))

    def test_change_request_holds_even_with_no_open_threads(self):
        self.assertHandoff([bot("CHANGES_REQUESTED", 10)], "changes", 0, thread("T1", resolved=True))

    def test_change_request_outranks_open_threads(self):
        self.assertHandoff([bot("APPROVED", 10), human("CHANGES_REQUESTED", 11)], "changes", 1, thread("T1"))

    # GitHub lists reviews oldest first, so in every fixture the first review is the stale one
    def test_a_reviewers_latest_verdict_replaces_their_earlier_one(self):
        self.assertHandoff([bot("APPROVED", 10), bot("CHANGES_REQUESTED", 11)], "changes")
        self.assertHandoff([bot("APPROVED", 10), bot("CHANGES_REQUESTED", 11), bot("APPROVED", 12)], "pass")

    def test_a_comment_changes_no_ones_standing(self):
        self.assertHandoff([bot("APPROVED", 10), bot("COMMENTED", 11)], "pass")
        self.assertHandoff([bot("CHANGES_REQUESTED", 10), bot("COMMENTED", 11)], "changes")
        self.assertHandoff([bot("APPROVED", 10), human("COMMENTED", 11, "Nice work.")], "pass")

    def test_comments_alone_are_not_a_pass(self):
        self.assertHandoff([human("COMMENTED", 10, "Nice work."), bot("COMMENTED", 11)], "pending")

    def test_a_dismissed_review_no_longer_counts(self):
        # GitHub turns a dismissed review's state into DISMISSED
        self.assertHandoff([bot("APPROVED", 10), human("DISMISSED", 11, "Rename this first.")], "pass")
        self.assertHandoff([bot("DISMISSED", 10)], "pending", 0)

    def test_a_pending_review_is_not_submitted_yet(self):
        self.assertHandoff([bot("APPROVED", 10), pending(HUMAN)], "pass")


class PerReviewerTest(HandoffCase):
    """Each reviewer's latest formal review counts separately, as on GitHub.

    The bot isn't the PR's author, so it gives formal APPROVE and REQUEST_CHANGES verdicts,
    and so can a human reviewer who isn't the author. A change request blocks until the
    same reviewer approves later or it is dismissed; another reviewer's approval doesn't
    lift it. GitHub refuses both verdicts from the author (422), so in v1 the user gives
    theirs in chat and nothing on the PR carries it.
    """

    def test_another_reviewers_verdict_counts(self):
        self.assertHandoff([human("APPROVED", 10)], "pass", 0, thread("T1", resolved=True))
        self.assertHandoff([human("CHANGES_REQUESTED", 10)], "changes", 0, thread("T1", resolved=True))

    def test_another_reviewers_change_request_blocks_a_bot_pass(self):
        rename = human("CHANGES_REQUESTED", 10, "Rename this first.")
        self.assertHandoff([rename, bot("APPROVED", 11)], "changes")
        self.assertHandoff([bot("APPROVED", 9), rename], "changes")

    def test_a_bot_change_request_blocks_another_reviewers_approval(self):
        self.assertHandoff([bot("CHANGES_REQUESTED", 10), human("APPROVED", 11)], "changes")
        self.assertHandoff([human("APPROVED", 10), bot("CHANGES_REQUESTED", 11)], "changes")

    def test_a_change_request_lifts_when_the_same_reviewer_approves(self):
        self.assertHandoff([bot("CHANGES_REQUESTED", 10), bot("APPROVED", 11)], "pass")
        self.assertHandoff([human("CHANGES_REQUESTED", 10), bot("APPROVED", 11), human("APPROVED", 12)], "pass")

    def test_a_change_request_lifts_when_it_is_dismissed(self):
        self.assertHandoff([human("DISMISSED", 10, "Rename this first."), bot("APPROVED", 11)], "pass")

    def test_a_comment_does_not_lift_a_change_request(self):
        self.assertHandoff(
            [
                human("CHANGES_REQUESTED", 10, "Rename this first."),
                bot("APPROVED", 11),
                human("COMMENTED", 12, "Done?"),
            ],
            "changes",
        )

    def test_another_reviewers_approval_does_not_close_open_threads(self):
        self.assertHandoff([human("APPROVED", 10)], "approved", 2, thread("T1"), thread("T2"))
        self.assertHandoff([human("APPROVED", 10)], "pass", 0, thread("T1", resolved=True), thread("T2", resolved=True))


class VerdictRoundTripTest(unittest.TestCase):
    """What the bot's submit writes is what handoff reads."""

    STATES = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED", "COMMENT": "COMMENTED"}

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def posted_review(self, verdict):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        gh.run("--pr", "5", "submit", verdict, "Summary.")
        (sent,) = gh.review_posts()
        # GitHub stores the event as a review state, under the bot's login
        return {
            "user": {"login": BOT, "type": "Bot"},
            "state": self.STATES[sent["event"]],
            "body": sent.get("body", ""),
            "submitted_at": "2026-10-10T10:00:00Z",
        }

    def test_each_verdict_reads_back_the_same(self):
        for verdict in ("pass", "changes"):
            with self.subTest(verdict=verdict):
                got = handoff(response(), [self.posted_review(verdict)])
                self.assertEqual(got["state"], verdict)


class StatusCliTest(unittest.TestCase):
    """`status` reads the PR's reviews and threads and reports the handoff."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(self.gh.cleanup)

    def status(self, reviews, *resolved):
        """Run status on `reviews` and threads whose isResolved are `resolved`.

        Returns the text output, lowercased, and what `status --json` reports.
        """
        self.gh.set_answer("GET /reviews", pages=pages(reviews))
        self.gh.set_answer("graphql reviewThreads", json.dumps(resolved_response(*resolved)))
        text = self.gh.run("--pr", "5", "status").stdout.lower()
        got = json.loads(self.gh.run("--pr", "5", "status", "--json").stdout)
        return text, (got["state"], got["open"])

    def test_reports_an_outstanding_change_request(self):
        text, got = self.status([bot("APPROVED", 10), human("CHANGES_REQUESTED", 11, "Rename first.")], True)
        self.assertEqual(got, ("changes", 0))
        self.assertIn("changes", text)

    def test_reads_past_the_first_page_of_reviews(self):
        # 30 reviews to a page, oldest first, so the bot's latest verdict is on page 2
        older = [by(BOT, "CHANGES_REQUESTED", 0, kind="Bot") for _ in range(30)]
        newer = [bot("APPROVED", 10), human("DISMISSED", 11, "Rename first."), pending(HUMAN)]
        text, got = self.status(older + newer)
        self.assertEqual(got, ("pass", 0))
        self.assertRegex(text, r"\bpass\b")

    def test_reports_how_many_threads_are_still_open(self):
        text, got = self.status([human("APPROVED", 10)], False, False, True)
        self.assertEqual(got, ("approved", 2), "resolved threads aren't counted")
        self.assertIn("approved", text)
        self.assertRegex(text, r"\b2\b")

    def test_counts_an_open_thread_past_the_first_page_of_threads(self):
        # GitHub serves at most 100 threads a page, so the open one is on page 2
        _, got = self.status([bot("APPROVED", 10)], *[True] * 100, False)
        self.assertEqual(got, ("approved", 1))


if __name__ == "__main__":
    unittest.main()
