"""#10: the bot verifies a fix, and the user's own login resolves only threads the bot verified.

GitHub refuses resolveReviewThread from an app with only pull_requests:write (it needs
contents:write), and the bot gets no write access to code. So the two acts are split:
`verify` is the bot's reply that the fix is in a commit of the PR, and `resolve` runs as the
user, only on threads where that reply is still the last word.
"""
import unittest

from helpers import BOT_SLUG, INSTALL_URL, Repo, bot_reply, git, node
from helpers import fake_with_threads as fake

USER = "AH-Merii"  # the PR's author, whose own gh login resolve runs as
HUMAN = "octocat"  # another reviewer


def verification(note=None):
    """The body `verify` posts as the bot."""
    return bot_reply("verify", *([note] if note else []))


class VerifyTest(unittest.TestCase):
    """`verify T SHA [NOTE]` is the bot's reply in thread T that the fix is verified in SHA.

    It posts one reply, as the bot, in thread T, naming SHA and carrying the note if one is
    given. It refuses and posts nothing unless SHA is in the history of the PR's current head
    on GitHub: not merely a commit the clone holds, nor one only the local branch has. Without
    the bot it posts nothing and says how to set the bot up; it never posts as the user.
    """

    def fresh(self):
        """A PR whose head is a fix on top of its first commit; returns that first commit."""
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        first = self.repo.head
        self.repo.head = self.commit("the fix")
        return first

    def commit(self, message):
        self.repo.write("other.py", self.repo.read("other.py") + message + "\n")
        git(self.repo.path, "commit", "-qam", message)
        return git(self.repo.path, "rev-parse", "HEAD")

    def gh(self, token="BOT_TOKEN"):
        gh = fake(self.repo, token, node("T1", (BOT_SLUG, "Rename this.")))
        self.addCleanup(gh.cleanup)
        return gh

    def assertPostedNothing(self, gh, out, why):
        self.assertNotEqual(out.returncode, 0, f"verify went through: {out.stdout}")
        self.assertEqual(gh.writes(), [], why)
        self.assertNotIn("Traceback", out.stderr)

    def test_posts_one_reply_as_the_bot_naming_the_commit(self):
        for which in ("the PR head", "an earlier commit of the PR"):
            for note in (None, "Checked the else branch too."):
                with self.subTest(which, note=note):
                    first = self.fresh()
                    sha = self.repo.head if which == "the PR head" else first
                    gh = self.gh()
                    out = gh.run("--pr", "5", "verify", "T1", sha, *([note] if note else []), check=False)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    (write,) = gh.writes()
                    self.assertEqual(write["fields"], ["addPullRequestReviewThreadReply"])
                    self.assertEqual(write["gh_token"], "BOT_TOKEN", "the bot verifies, not the user")
                    (reply,) = write["replies"]
                    self.assertEqual(reply["thread"], "T1")
                    self.assertIn(sha, reply["body"], "the reply names the verified commit")
                    self.assertRegex(reply["body"], r"(?i)\bverified\b")
                    if note:
                        self.assertIn(note, reply["body"])

    def test_refuses_a_commit_outside_the_pr_heads_history(self):
        for case in ("no such commit", "the head before a force-push",
                     "a commit on the base branch only", "a local commit not pushed yet"):
            with self.subTest(case):
                self.fresh()
                if case == "no such commit":
                    sha = "0123456789abcdef" * 2 + "01234567"
                elif case == "the head before a force-push":
                    # the clone follows the rewritten PR but still holds the old head
                    sha = self.repo.head
                    git(self.repo.path, "commit", "-q", "--amend", "-m", "the fix, reworded")
                    self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
                elif case == "a commit on the base branch only":
                    git(self.repo.path, "checkout", "-q", "main")
                    sha = self.commit("main moved on")
                    git(self.repo.path, "checkout", "-q", "feature")
                else:
                    # the PR head stays at self.repo.head; only the local branch moves on
                    sha = self.commit("not pushed")
                gh = self.gh()
                out = gh.run("--pr", "5", "verify", "T1", sha, check=False)
                self.assertPostedNothing(gh, out, f"verified {case}")
                self.assertIn(sha[:7], out.stderr, "the refusal names the commit it turned down")

    def test_without_the_bot_nothing_is_posted(self):
        self.fresh()
        gh = self.gh(token=None)
        out = gh.run("--pr", "5", "verify", "T1", self.repo.head, check=False)
        self.assertPostedNothing(gh, out, "no fallback to the user's login: the bot verifies")
        self.assertIn(INSTALL_URL, out.stderr, "it says how to set the bot up for this repo")


class ResolveTest(unittest.TestCase):
    """`resolve T...` runs as the user's own gh login, and only on threads the bot verified.

    A thread passes only when its latest comment is a verification the bot wrote. A
    verification written or pasted by anyone else doesn't count, a bot comment that isn't a
    verification doesn't count, and neither does a verification with any comment after it,
    from anyone. Every thread goes in one request, and only if all of them pass; otherwise
    nothing is resolved and the refusal names each failing thread, one to a line, and why.
    Resolving needs nothing from the bot's token.
    """

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def resolve(self, threads, ids, token="BOT_TOKEN"):
        """Run `resolve ids` on PR 5 holding `threads`; return the run and the writes it made."""
        gh = fake(self.repo, token, *threads)
        self.addCleanup(gh.cleanup)
        out = gh.run("--pr", "5", "resolve", *ids, check=False)
        return out, gh.writes()

    def test_verified_threads_resolve_in_one_request_as_the_user(self):
        verified = verification()
        cases = {
            "one thread": [
                node("T_a", (BOT_SLUG, "Rename this."), (USER, "Fixed in abc1234."), (BOT_SLUG, verified))],
            "several threads": [
                node("T_a", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified)),
                node("T_b", (BOT_SLUG, "Why?"), (USER, "Fixed."),
                     (BOT_SLUG, verification("Checked the else branch too."))),
                # pushback, then the bot verified again: its verification is the last word
                node("T_c", (BOT_SLUG, "Off by one."), (BOT_SLUG, verified),
                     (USER, "Still off on an empty list."), (BOT_SLUG, verified))],
        }
        for token in ("BOT_TOKEN", None):
            for name, threads in cases.items():
                with self.subTest(name, bot="installed" if token else "not installed"):
                    ids = [t["id"] for t in threads]
                    out, writes = self.resolve(threads, ids, token)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    (write,) = writes
                    self.assertEqual(write["fields"], ["resolveReviewThread"] * len(ids))
                    self.assertEqual(sorted(write["threads"]), sorted(ids), "each names its own thread")
                    self.assertIsNone(write["gh_token"], "resolve runs as the user's login, not the bot's")

    def test_one_thread_without_the_bots_last_word_stops_them_all(self):
        verified = verification()
        sha = self.repo.head
        cases = {
            "only the bot's review comment": [(BOT_SLUG, "Rename this.")],
            "the author says it's fixed": [(BOT_SLUG, "Rename this."), (USER, f"Fixed in {sha}.")],
            "a bot comment naming a commit, not a verification":
                [(BOT_SLUG, "Rename this."), (BOT_SLUG, f"Not verified: {sha} still misses the else branch.")],
            "the verification pasted by the author": [(BOT_SLUG, "Rename this."), (USER, verified)],
            "the verification posted by another bot": [(BOT_SLUG, "Rename this."), ("github-actions", verified)],
            "the verification by a login that starts like the bot's":
                [(BOT_SLUG, "Rename this."), (BOT_SLUG + "-fan", verified)],
            "the verification by a deleted account": [(BOT_SLUG, "Rename this."), (None, verified)],
            "the author pushed back after it": [(BOT_SLUG, verified), (USER, "That isn't the fix I meant.")],
            "another reviewer commented after it": [(BOT_SLUG, verified), (HUMAN, "The tests still fail.")],
            "the bot commented after its own verification":
                [(BOT_SLUG, verified), (BOT_SLUG, "One more thing: rename the test too.")],
            "not a thread on this PR": None,
        }
        ok = node("T_ok", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified))
        for name, comments in cases.items():
            with self.subTest(name):
                threads = [ok] + ([node("T_bad", *comments)] if comments is not None else [])
                out, writes = self.resolve(threads, ["T_ok", "T_bad"])
                self.assertNotEqual(out.returncode, 0, f"resolve went through: {out.stdout}")
                self.assertEqual(writes, [], "nothing is resolved, not even the verified thread")
                self.assertIn("T_bad", out.stderr, "the refusal names the failing thread")
                self.assertNotIn("Traceback", out.stderr)

    def test_the_refusal_says_why_each_thread_fails(self):
        verified = verification()
        threads = [
            node("T_ok", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified)),
            node("T_unverified", (BOT_SLUG, "Rename this."), (USER, "Fixed.")),
            node("T_pasted", (BOT_SLUG, "Rename this."), (USER, verified)),
            node("T_pushback", (BOT_SLUG, "Rename this."), (BOT_SLUG, verified), (USER, "Fixed?")),
        ]
        out, writes = self.resolve(threads, [t["id"] for t in threads])
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(writes, [])
        reasons = {}
        for id in ("T_unverified", "T_pasted", "T_pushback"):
            lines = [line for line in out.stderr.splitlines() if id in line]
            self.assertTrue(lines, f"the refusal doesn't name {id}: {out.stderr}")
            reasons[id] = " ".join(lines).replace(id, "").strip()
        self.assertEqual(len(set(reasons.values())), 3,
                         f"three different failures read as fewer reasons: {reasons}")
        self.assertRegex(reasons["T_pasted"], rf"(?i)\bbot\b|{USER}", "says who wrote the verification")
        self.assertRegex(reasons["T_pushback"], r"(?i)\b(after|since|later|newer|follow\w*)\b",
                         "says something came after the verification")


if __name__ == "__main__":
    unittest.main()
