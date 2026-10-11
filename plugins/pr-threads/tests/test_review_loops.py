"""Pushback on review threads. The bot accepts or disputes the author's pushback on its
thread, and status reports the disputed threads and the round, so a review can tell what's
still contested and how many verdicts it has taken.

`withdraw` is the bot's reply accepting the author's pushback; `dispute` is its reply
rejecting it. Threads here are built from what those verbs
and `verify` actually post, so no test depends on how a marker is spelled.
"""

import json
import re
import unittest

from helpers import BOT, BOT_SLUG, INSTALL_URL, Repo, bot_reply, node, pages
from helpers import fake_with_threads as fake

USER = "AH-Merii"  # the PR's author
HUMAN = "octocat"  # another reviewer
REASON = "Tried it in #12; the cache made it slower."


def verified():
    return bot_reply("verify")


def withdrawn():
    return bot_reply("withdraw", REASON)


def disputed():
    return bot_reply("dispute", "The cache was cold in #12; measure it warm.")


def reopened():
    return bot_reply("reopen", "The fix in #12 still misses an empty list.")


class PushbackRepliesTest(unittest.TestCase):
    """`withdraw T REASON` and `dispute T REASON` each post one reply in T, as the bot, with the reason.

    Neither takes an empty or blank reason: the reason is the record of why the finding was
    dropped or kept. Without the bot neither posts anything; they show the install link and
    never fall back to the user's login.
    """

    VERBS = ("withdraw", "dispute")

    def run_verb(self, verb, reason, token="BOT_TOKEN"):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        gh = fake(repo, token, node("T1", (BOT_SLUG, "Cache this."), (USER, REASON)))
        self.addCleanup(gh.cleanup)
        return gh, gh.run("--pr", "5", verb, "T1", reason, check=False)

    def assertPosted(self, gh, out, reason):
        self.assertEqual(out.returncode, 0, out.stderr)
        (write,) = gh.writes()
        self.assertEqual(write["fields"], ["addPullRequestReviewThreadReply"])
        self.assertEqual(write["gh_token"], "BOT_TOKEN", "the bot replies, not the user")
        (reply,) = write["replies"]
        self.assertEqual(reply["thread"], "T1")
        self.assertIn(reason, reply["body"])

    def test_each_posts_one_reply_as_the_bot_with_its_reason(self):
        for verb in self.VERBS:
            with self.subTest(verb):
                gh, out = self.run_verb(verb, "Agreed: the decision in #9 rules this out.")
                self.assertPosted(gh, out, "Agreed: the decision in #9 rules this out.")

    def test_an_empty_reason_is_refused(self):
        for verb in self.VERBS:
            for reason in ("", "   ", "\n\t"):
                with self.subTest(verb, reason=reason):
                    gh, out = self.run_verb(verb, reason)
                    self.assertNotEqual(out.returncode, 0, f"{verb} went through: {out.stdout}")
                    self.assertEqual(gh.writes(), [], "nothing is posted")
                    self.assertIn("reason", out.stderr.lower(), "the refusal asks for a reason")
                    self.assertNotIn("Traceback", out.stderr)
            with self.subTest(verb, reason="a real one"):
                gh, out = self.run_verb(verb, "x")
                self.assertPosted(gh, out, "x")

    def test_without_the_bot_nothing_is_posted(self):
        for verb in self.VERBS:
            with self.subTest(verb):
                gh, out = self.run_verb(verb, REASON, token=None)
                self.assertNotEqual(out.returncode, 0)
                self.assertEqual(gh.writes(), [], "no fallback to the user's login")
                self.assertIn(INSTALL_URL, out.stderr, "it says how to set the bot up for this repo")


class PushbackResolveTest(unittest.TestCase):
    """resolve honours the bot's withdrawal exactly as it honours its verification.

    A thread resolves when its latest comment is a withdrawal or a verification the bot
    wrote, with nothing after it. A disputed thread is refused, and the refusal says it is
    disputed: a thread is disputed while the bot's latest verdict on it (verification,
    withdrawal or dispute) is a dispute, even if the author argued on after it.
    """

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def resolve(self, threads, ids):
        gh = fake(self.repo, "BOT_TOKEN", *threads)
        self.addCleanup(gh.cleanup)
        out = gh.run("--pr", "5", "resolve", *ids, check=False)
        return out, gh.writes()

    def test_withdrawn_threads_resolve_like_verified_ones(self):
        cases = {
            "withdrawn": [node("T_a", (BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, withdrawn()))],
            "disputed, then withdrawn": [
                node(
                    "T_a",
                    (BOT_SLUG, "Cache this."),
                    (USER, REASON),
                    (BOT_SLUG, disputed()),
                    (USER, "Warm, it's still slower."),
                    (BOT_SLUG, withdrawn()),
                )
            ],
            "disputed, then fixed and verified": [
                node("T_a", (BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed()), (BOT_SLUG, verified()))
            ],
            "withdrawn and verified threads together": [
                node("T_a", (BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, withdrawn())),
                node("T_b", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified())),
            ],
        }
        for name, threads in cases.items():
            with self.subTest(name):
                ids = [t["id"] for t in threads]
                out, writes = self.resolve(threads, ids)
                self.assertEqual(out.returncode, 0, out.stderr)
                (write,) = writes
                self.assertEqual(write["fields"], ["resolveReviewThread"] * len(ids))
                self.assertEqual(sorted(write["threads"]), sorted(ids))
                self.assertIsNone(write["gh_token"], "resolve runs as the user's login, not the bot's")

    def test_a_withdrawal_counts_only_from_the_bot_with_nothing_after_it(self):
        cases = {
            "pasted by the author": [(BOT_SLUG, "Cache this."), (USER, withdrawn())],
            "posted by another bot": [(BOT_SLUG, "Cache this."), ("github-actions", withdrawn())],
            "the author commented after it": [(BOT_SLUG, withdrawn()), (USER, "Thanks, but also...")],
            "the bot commented after it": [(BOT_SLUG, withdrawn()), (BOT_SLUG, "On second thought...")],
        }
        ok = node("T_ok", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified()))
        for name, comments in cases.items():
            with self.subTest(name):
                out, writes = self.resolve([ok, node("T_bad", *comments)], ["T_ok", "T_bad"])
                self.assertNotEqual(out.returncode, 0, f"resolve went through: {out.stdout}")
                self.assertEqual(writes, [], "nothing is resolved, not even the verified thread")
                self.assertIn("T_bad", out.stderr)
                self.assertNotIn("Traceback", out.stderr)

    def test_a_disputed_thread_is_refused_as_disputed(self):
        cases = {
            "the bot disputed the pushback": [(BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed())],
            "the author argued on after the dispute": [
                (BOT_SLUG, "Cache this."),
                (USER, REASON),
                (BOT_SLUG, disputed()),
                (USER, "It is warm."),
            ],
            "disputed after a withdrawal": [(BOT_SLUG, withdrawn()), (USER, "Thanks."), (BOT_SLUG, disputed())],
            "disputed after a verification": [(BOT_SLUG, verified()), (USER, "Not that."), (BOT_SLUG, disputed())],
            "a verification pasted after the dispute": [(BOT_SLUG, disputed()), (USER, verified())],
        }
        ok = node("T_ok", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified()))
        for name, comments in cases.items():
            with self.subTest(name):
                out, writes = self.resolve([ok, node("T_bad", *comments)], ["T_ok", "T_bad"])
                self.assertNotEqual(out.returncode, 0, f"resolve went through: {out.stdout}")
                self.assertEqual(writes, [], "nothing is resolved, not even the verified thread")
                lines = " ".join(line for line in out.stderr.splitlines() if "T_bad" in line)
                self.assertRegex(lines, r"(?i)disput", f"the refusal doesn't say T_bad is disputed: {out.stderr}")


class ReopenReplyTest(PushbackRepliesTest):
    """`reopen T REASON` is the bot's reply that the fix in T didn't work.

    It follows the rules of withdraw and dispute: one reply in T, as the bot, with its
    reason; no empty or blank reason; without the bot, the install link and nothing posted.
    """

    VERBS = ("reopen",)


class ReopenStateTest(unittest.TestCase):
    """A thread the bot reopened is open, isn't disputed, and doesn't resolve.

    The bot's latest verdict decides a thread's state: a reopen after a dispute ends the
    dispute, a dispute after a reopen is a dispute, and a verification or withdrawal after
    a reopen lets the thread resolve. Only the bot's own reopen counts.
    """

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def status(self, *threads):
        """(text output, status --json) for a PR the bot approved, with review `threads`."""
        gh = fake(self.repo, "BOT_TOKEN", *threads)
        self.addCleanup(gh.cleanup)
        gh.set_answer("GET /reviews", pages=pages([bot("APPROVED", 10)]))
        text = gh.run("--pr", "5", "status").stdout
        return text, json.loads(gh.run("--pr", "5", "status", "--json").stdout)

    def resolve(self, threads, ids):
        gh = fake(self.repo, "BOT_TOKEN", *threads)
        self.addCleanup(gh.cleanup)
        out = gh.run("--pr", "5", "resolve", *ids, check=False)
        return out, gh.writes()

    def test_status_reads_the_bots_latest_verdict(self):
        plain = node("T_plain", (BOT_SLUG, "Rename this."), resolved=False)
        cases = {
            "reopened after the author said it's fixed": (
                False,
                [(BOT_SLUG, "Cache this."), (USER, "Fixed."), (BOT_SLUG, reopened())],
            ),
            "reopened after a verification": (
                False,
                [(BOT_SLUG, "Cache this."), (BOT_SLUG, verified()), (BOT_SLUG, reopened())],
            ),
            "the author argued on after a reopen": (
                False,
                [(BOT_SLUG, "Cache this."), (BOT_SLUG, reopened()), (USER, "It works here.")],
            ),
            "reopened after a dispute": (
                False,
                [
                    (BOT_SLUG, "Cache this."),
                    (USER, REASON),
                    (BOT_SLUG, disputed()),
                    (USER, "Fixed it your way."),
                    (BOT_SLUG, reopened()),
                ],
            ),
            "disputed after a reopen": (
                True,
                [(BOT_SLUG, "Cache this."), (BOT_SLUG, reopened()), (USER, REASON), (BOT_SLUG, disputed())],
            ),
            "a reopen pasted by the author after a dispute": (
                True,
                [(BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed()), (USER, reopened())],
            ),
        }
        for name, (is_disputed, comments) in cases.items():
            with self.subTest(name):
                text, got = self.status(plain, node("T_x", *comments, resolved=False))
                self.assertEqual(got["disputed"], ["T_x"] if is_disputed else [])
                self.assertEqual(
                    (got["state"], got["open"]), ("approved", 2), "a reopened thread is still open, and blocks pass"
                )
                clause = re.search(r"(?i)\bdisputed:\s*([^;\n]*)", text)
                listed = clause[1] if clause else ""
                if is_disputed:
                    self.assertIn("T_x", listed, f"the text doesn't list T_x as disputed: {text}")
                else:
                    self.assertNotIn("T_x", listed, f"the text lists T_x as disputed: {text}")
        with self.subTest("only a reopened thread open still blocks pass"):
            only = node(
                "T_x", (BOT_SLUG, "Cache this."), (BOT_SLUG, verified()), (BOT_SLUG, reopened()), resolved=False
            )
            _, got = self.status(only)
            self.assertEqual((got["disputed"], got["state"], got["open"]), ([], "approved", 1))

    def test_resolve_refuses_a_reopened_thread(self):
        cases = {
            "reopened after the author said it's fixed": [
                (BOT_SLUG, "Cache this."),
                (USER, "Fixed."),
                (BOT_SLUG, reopened()),
            ],
            "verified, then reopened": [(BOT_SLUG, "Cache this."), (BOT_SLUG, verified()), (BOT_SLUG, reopened())],
            "withdrawn, then reopened": [
                (BOT_SLUG, "Cache this."),
                (USER, REASON),
                (BOT_SLUG, withdrawn()),
                (BOT_SLUG, reopened()),
            ],
            "reopened after a dispute": [(BOT_SLUG, "Cache this."), (BOT_SLUG, disputed()), (BOT_SLUG, reopened())],
            "the author replied after a reopen": [
                (BOT_SLUG, "Cache this."),
                (BOT_SLUG, verified()),
                (BOT_SLUG, reopened()),
                (USER, "Now?"),
            ],
        }
        ok = node("T_ok", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified()))
        for name, comments in cases.items():
            with self.subTest(name):
                out, writes = self.resolve([ok, node("T_bad", *comments)], ["T_ok", "T_bad"])
                self.assertNotEqual(out.returncode, 0, f"resolve went through: {out.stdout}")
                self.assertEqual(writes, [], "nothing is resolved, not even the verified thread")
                self.assertIn("T_bad", out.stderr)
                self.assertNotIn("Traceback", out.stderr)
                if comments[-1][0] == BOT_SLUG:
                    # the bot's own reopen is the last word: say so, not that someone else wrote it
                    lines = " ".join(line for line in out.stderr.splitlines() if "T_bad" in line)
                    self.assertRegex(lines, r"(?i)reopen", f"the refusal doesn't say T_bad was reopened: {out.stderr}")
                    self.assertNotRegex(
                        lines, r"(?i)not the bot", f"the refusal disowns the bot's reopen: {out.stderr}"
                    )
        with self.subTest("disputed after a reopen"):
            comments = [(BOT_SLUG, "Cache this."), (BOT_SLUG, reopened()), (BOT_SLUG, disputed())]
            out, writes = self.resolve([ok, node("T_bad", *comments)], ["T_ok", "T_bad"])
            self.assertEqual((out.returncode != 0, writes), (True, []))
            lines = " ".join(line for line in out.stderr.splitlines() if "T_bad" in line)
            self.assertRegex(lines, r"(?i)disput", f"the refusal doesn't say T_bad is disputed: {out.stderr}")

    def test_a_reopened_thread_resolves_once_the_bot_verifies_or_withdraws_again(self):
        cases = {
            "reopened, then fixed and verified": [
                (BOT_SLUG, "Cache this."),
                (BOT_SLUG, verified()),
                (BOT_SLUG, reopened()),
                (USER, "Fixed for real."),
                (BOT_SLUG, verified()),
            ],
            "reopened, then withdrawn": [
                (BOT_SLUG, "Cache this."),
                (BOT_SLUG, reopened()),
                (USER, REASON),
                (BOT_SLUG, withdrawn()),
            ],
        }
        for name, comments in cases.items():
            with self.subTest(name):
                out, writes = self.resolve([node("T_a", *comments)], ["T_a"])
                self.assertEqual(out.returncode, 0, out.stderr)
                (write,) = writes
                self.assertEqual(write["threads"], ["T_a"])


def review(login, state, hour, kind="User"):
    """A submitted review as GitHub's REST API lists it."""
    return {
        "user": {"login": login, "type": kind},
        "state": state,
        "body": "",
        "submitted_at": f"2026-10-10T{hour % 24:02d}:00:00Z",
    }


def bot(state, hour):
    return review(BOT, state, hour, kind="Bot")


class StatusLoopTest(unittest.TestCase):
    """status reports what bounds the loop: the open disputes, and the round.

    `disputed` lists the open threads whose bot's latest verdict is a dispute: a later bot
    verification or withdrawal ends it, the author arguing on doesn't, and only the bot's own
    dispute counts. A disputed thread is still open: `open` counts it and it blocks `pass`.
    `round` is how many verdicts the bot has submitted on the PR; only reporting it, not
    capping it. Other reviewers' reviews don't count, and a dismissed bot verdict still does.
    The bot's COMMENTED reviews are not rounds: submit only sends APPROVE or REQUEST_CHANGES,
    and GitHub wraps each of the bot's thread replies (verify, withdraw, dispute) in a
    COMMENTED review of its own.
    """

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def status(self, reviews, *threads):
        """(text output, status --json) for a PR with `reviews` and review `threads`."""
        gh = fake(self.repo, "BOT_TOKEN", *threads)
        self.addCleanup(gh.cleanup)
        gh.set_answer("GET /reviews", pages=pages(reviews))
        text = gh.run("--pr", "5", "status").stdout
        return text, json.loads(gh.run("--pr", "5", "status", "--json").stdout)

    def test_disputed_threads_are_reported_apart_from_other_open_threads(self):
        plain = node("T_plain", (BOT_SLUG, "Rename this."), resolved=False)
        cases = {
            "the bot disputed the pushback": (
                True,
                [(BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed())],
            ),
            "the author argued on after the dispute": (
                True,
                [(BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed()), (USER, "It is warm.")],
            ),
            "disputed after a verification": (
                True,
                [(BOT_SLUG, verified()), (USER, "Not that."), (BOT_SLUG, disputed())],
            ),
            "withdrawn after the dispute": (
                False,
                [(BOT_SLUG, disputed()), (USER, "Warm, still slower."), (BOT_SLUG, withdrawn())],
            ),
            "verified after the dispute": (False, [(BOT_SLUG, disputed()), (BOT_SLUG, verified())]),
            "a verification pasted after the dispute": (True, [(BOT_SLUG, disputed()), (USER, verified())]),
            "a withdrawal pasted after the dispute": (True, [(BOT_SLUG, disputed()), (USER, withdrawn())]),
            "a dispute pasted by the author": (False, [(BOT_SLUG, "Cache this."), (USER, disputed())]),
            "pushback the bot hasn't answered": (False, [(BOT_SLUG, "Cache this."), (USER, REASON)]),
        }
        for name, (is_disputed, comments) in cases.items():
            with self.subTest(name):
                text, got = self.status([bot("APPROVED", 10)], plain, node("T_x", *comments, resolved=False))
                self.assertIn("disputed", got, f"status --json doesn't report disputes: {got}")
                self.assertEqual(got["disputed"], ["T_x"] if is_disputed else [])
                self.assertEqual(
                    (got["state"], got["open"]), ("approved", 2), "a disputed thread is still open, and blocks pass"
                )
                if is_disputed:
                    self.assertRegex(text, r"(?i)disput", f"the text doesn't mention the dispute: {text}")
                    self.assertIn("T_x", text, "the text names the disputed thread")
        with self.subTest("a resolved thread isn't disputed"):
            gone = node("T_x", (BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed()), resolved=True)
            _, got = self.status([bot("APPROVED", 10)], gone)
            self.assertEqual((got.get("disputed"), got["state"]), ([], "pass"))
        with self.subTest("only a dispute open still blocks pass"):
            only = node("T_x", (BOT_SLUG, "Cache this."), (USER, REASON), (BOT_SLUG, disputed()), resolved=False)
            _, got = self.status([bot("APPROVED", 10)], only)
            self.assertEqual((got.get("disputed"), got["state"], got["open"]), (["T_x"], "approved", 1))

    def test_round_counts_the_reviews_the_bot_submitted(self):
        others = [
            review(HUMAN, "APPROVED", 1),
            review(HUMAN, "CHANGES_REQUESTED", 2),
            review(USER, "COMMENTED", 3),
            review("github-actions[bot]", "COMMENTED", 4, kind="Bot"),
        ]
        cases = {
            "no reviews": ([], 0),
            "one bot review": ([bot("CHANGES_REQUESTED", 10)], 1),
            "several bot reviews": (
                [bot("CHANGES_REQUESTED", 10), bot("CHANGES_REQUESTED", 11), bot("APPROVED", 12)],
                3,
            ),
            "only other reviewers' reviews": (others, 0),
            "bot reviews among others'": (
                [others[0], bot("CHANGES_REQUESTED", 10), others[1], others[2], bot("APPROVED", 12), others[3]],
                2,
            ),
            "a dismissed bot review was still a round": ([bot("DISMISSED", 10), bot("APPROVED", 11)], 2),
            "bot reviews past the first page": ([bot("CHANGES_REQUESTED", h) for h in range(31)] + others, 31),
        }
        for name, (reviews, want) in cases.items():
            with self.subTest(name):
                text, got = self.status(reviews)
                self.assertIn("round", got, f"status --json doesn't report the round: {got}")
                self.assertEqual(got["round"], want)
                self.assertRegex(text, rf"(?i)\bround\D*\b{want}\b", f"the text doesn't give round {want}: {text}")

    def test_the_bots_comment_reviews_are_not_rounds(self):
        # what the live run on AH-Merii/test#7 listed: a verdict, a COMMENTED review around each
        # verify reply, then the next verdict; status said round 4
        replies = lambda hour, n: [bot("COMMENTED", hour + i) for i in range(n)]
        cases = {
            "a comment review per reply between two verdicts": (
                [bot("CHANGES_REQUESTED", 1)] + replies(2, 2) + [bot("APPROVED", 5)],
                2,
            ),
            "comment reviews only": (replies(1, 3), 0),
            "comment reviews after the last verdict": ([bot("CHANGES_REQUESTED", 1)] + replies(2, 3), 1),
            "a dismissed verdict among comment reviews": (
                [bot("DISMISSED", 1)]
                + replies(2, 2)
                + [bot("CHANGES_REQUESTED", 5)]
                + replies(6, 1)
                + [bot("APPROVED", 8)],
                3,
            ),
            "comment reviews past the first page": (
                [bot("CHANGES_REQUESTED", 0)] + replies(1, 31) + [bot("APPROVED", 9)],
                2,
            ),
        }
        for name, (reviews, want) in cases.items():
            with self.subTest(name):
                text, got = self.status(reviews)
                self.assertEqual(got.get("round"), want, "only the bot's verdicts are rounds")
                self.assertRegex(text, rf"(?i)\bround\D*\b{want}\b", f"the text doesn't give round {want}: {text}")


if __name__ == "__main__":
    unittest.main()
