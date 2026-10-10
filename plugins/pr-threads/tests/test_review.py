"""#9: comments are collected across separate commands and submitted as one review."""
import json
import re
import unittest

from helpers import INSTALL_URL, FakeGh, Repo, assert_keeps_local_work, assert_moves_to_pr_head, git, pr_table

from pr_threads.suggestions import parse_suggestion


class SubmitTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def gh(self, token="BOT_TOKEN"):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token=token)
        self.addCleanup(gh.cleanup)
        return gh

    def stage_two(self, gh):
        gh.run("--pr", "5", "comment", "app.py:10", "Why change this?")
        gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", input_text="x = 1\n")

    def test_staged_comments_go_out_together_in_one_request(self):
        gh = self.gh()
        self.stage_two(gh)
        self.assertEqual(gh.review_posts(), [], "nothing is posted before submit")
        gh.run("--pr", "5", "submit", "changes", "Two things to fix.")
        (review,) = gh.review_posts()
        self.assertEqual(len(review["comments"]), 2)
        self.assertEqual(review["commit_id"], self.repo.head)
        (suggestion,) = [c for c in review["comments"] if "```suggestion" in c["body"]]
        self.assertEqual((suggestion["path"], suggestion.get("start_line"), suggestion["line"]),
                         ("app.py", 21, 22), "the replacement covers both lines, not just the last")
        self.assertIn("```suggestion\nx = 1\n```", suggestion["body"])

    def test_bot_verdicts_are_formal_review_states(self):
        for verdict, event in (("changes", "REQUEST_CHANGES"), ("pass", "APPROVE")):
            with self.subTest(verdict=verdict):
                gh = self.gh()
                gh.run("--pr", "5", "submit", verdict, "Summary.")
                (review,) = gh.review_posts()
                self.assertEqual(review["event"], event)
                (post,) = [c for c in gh.calls("POST") if c["body"] == review]
                self.assertEqual(post["gh_token"], "BOT_TOKEN")

    def test_without_the_bot_nothing_is_submitted(self):
        # no fallback to the user's login: GitHub refuses the author's own verdict
        gh = self.gh(token=None)
        self.stage_two(gh)
        out = gh.run("--pr", "5", "submit", "changes", "Summary.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(gh.review_posts(), [], "nothing is posted")
        self.assertIn(INSTALL_URL, out.stderr, "it says how to set the bot up for this repo")

    def test_failed_submit_keeps_the_staged_comments(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.set_answer("POST /reviews", exit=1)
        self.assertNotEqual(gh.run("--pr", "5", "submit", "changes", "S.", check=False).returncode, 0)
        gh.set_answer("POST /reviews", json.dumps({"html_url": "u"}))
        gh.run("--pr", "5", "submit", "changes", "S.")
        self.assertEqual(len(gh.review_posts()[-1]["comments"]), 2)

    def test_successful_submit_starts_the_next_review_empty(self):
        gh = self.gh()
        self.stage_two(gh)
        gh.run("--pr", "5", "submit", "changes", "S.")
        gh.run("--pr", "5", "submit", "pass", "All good.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [])

    def test_line_outside_the_diff_is_refused_before_anything_is_staged(self):
        gh = self.gh()
        out = gh.run("--pr", "5", "comment", "app.py:1", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        gh.run("--pr", "5", "comment", "app.py:10", "This one is fine.")
        gh.run("--pr", "5", "submit", "changes", "S.")
        (sent,) = gh.review_posts()[-1]["comments"]
        self.assertEqual(sent["line"], 10)

    def test_comments_are_refused_while_the_local_branch_has_unpushed_commits(self):
        # issue #7: line numbers only mean something against the pushed head
        gh = self.gh()
        self.repo.write("other.py", "local only\n")
        git(self.repo.path, "commit", "-qam", "not pushed yet")
        for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
            with self.subTest(command=args[0]):
                out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("push", out.stderr.lower())
        git(self.repo.path, "reset", "-q", "--hard", self.repo.head)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "refused comments were not staged")

    def test_comments_are_refused_while_the_local_branch_is_behind_the_pr_head(self):
        # someone pushed to the PR since this clone last pulled
        local = self.repo.head
        self.repo.write("other.py", "pushed from elsewhere\n")
        git(self.repo.path, "commit", "-qam", "pushed from elsewhere")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        gh = self.gh()
        git(self.repo.path, "reset", "-q", "--hard", local)
        for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
            with self.subTest(command=args[0]):
                out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("pull", out.stderr.lower(), "the fix is to pull, not to push")
        git(self.repo.path, "reset", "-q", "--hard", self.repo.head)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "refused comments were not staged")

    def test_diverged_branch_is_told_how_to_get_back_without_pulling(self):
        reviewed = self.repo.head
        for case in ("rewritten", "both moved"):
            git(self.repo.path, "reset", "-q", "--hard", reviewed)
            if case == "rewritten":
                # the author amended and force-pushed after this clone checked the PR out
                git(self.repo.path, "commit", "-q", "--amend", "-m", "head, reworded")
            else:
                # the PR moved on while this clone made its own commit
                self.repo.write("app.py", self.repo.read("app.py") + "pushed from elsewhere\n")
                git(self.repo.path, "commit", "-qam", "pushed from elsewhere")
            self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
            gh = self.gh()
            git(self.repo.path, "reset", "-q", "--hard", reviewed)
            if case == "both moved":
                self.repo.write("other.py", "local only\n")
                git(self.repo.path, "commit", "-qam", "local only")
            local = git(self.repo.path, "rev-parse", "HEAD")
            for args in (("comment", "app.py:10", "Hmm."), ("suggest", "app.py:10", "Hmm.")):
                with self.subTest(case, command=args[0]):
                    out = gh.run("--pr", "5", *args, check=False, input_text="x\n")
                    self.assertNotEqual(out.returncode, 0)
                    if case == "both moved":
                        assert_keeps_local_work(self, out.stderr, local)
                    else:
                        assert_moves_to_pr_head(self, out.stderr)
            self.assertEqual(gh.review_posts(), [])

    def test_comments_are_refused_when_the_pr_head_was_never_fetched(self):
        self.repo.head = "0" * 40
        gh = self.gh()
        out = gh.run("--pr", "5", "comment", "app.py:10", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertRegex(out.stderr.lower(), r"\bfetch\b|\bpull\b")

    def test_comment_on_a_locally_edited_file_is_refused(self):
        gh = self.gh()
        pushed = self.repo.read("app.py")
        self.repo.write("app.py", "inserted\n" + pushed)
        out = gh.run("--pr", "5", "comment", "app.py:10", "Hmm.", check=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("app.py", out.stderr)
        self.assertRegex(out.stderr.lower(), r"uncommitted|modified|local", "the refusal says why")
        self.repo.write("app.py", pushed)
        gh.run("--pr", "5", "submit", "pass", "Nothing staged.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [], "the refused comment was not staged")


class MovedHeadCase(unittest.TestCase):
    """A comment staged on the reviewed head, after which the PR head moves.

    The author either pushes a commit on top or rewrites the PR and force-pushes; the
    local branch follows the PR, so the clone is in sync with the new head.
    """

    MOVES = ("pushed on top", "force-pushed")

    def staged_then_moved(self, move):
        """(fake gh, reviewed head) with one comment staged, after the PR head moved by `move`."""
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        gh.run("--pr", "5", "comment", "app.py:10", "Why change this?")
        reviewed = self.repo.head
        if move == "pushed on top":
            self.repo.write("other.py", "pushed after the review\n")
            git(self.repo.path, "commit", "-qam", "pushed after the review")
        else:
            git(self.repo.path, "commit", "-q", "--amend", "-m", "head, rewritten")
        self.repo.head = git(self.repo.path, "rev-parse", "HEAD")
        gh.set_answer("pr view 5", pr_table(self.repo)["pr view 5"]["stdout"])
        return gh, reviewed


class SubmitMovedHeadTest(MovedHeadCase):
    """submit never passes a head the reviewer didn't review.

    Once the PR head moved past the staged comments, `pass` is refused. `changes` may still
    go out, on the staged head its comments are pinned to: asking for changes on an older
    commit approves nothing.
    """

    def assertSaysTheHeadMoved(self, message, reviewed):
        shas = re.findall(r"\b[0-9a-f]{7,40}\b", message)
        names_a_head = any(h.startswith(sha) for sha in shas for h in (reviewed, self.repo.head))
        self.assertTrue(names_a_head or re.search(r"\b(moved|new commits?|since)\b", message, re.I),
                        f"the refusal doesn't say the PR has new commits: {message}")

    def test_pass_is_refused_once_the_pr_head_moved_past_the_staged_comments(self):
        for move in self.MOVES:
            with self.subTest(move=move):
                gh, reviewed = self.staged_then_moved(move)
                out = gh.run("--pr", "5", "submit", "pass", "Summary.", check=False)
                self.assertEqual(gh.review_posts(), [], f"a pass went out on {reviewed[:12]}, "
                                 f"though the PR is now at {self.repo.head[:12]}")
                self.assertNotEqual(out.returncode, 0)
                self.assertSaysTheHeadMoved(out.stderr, reviewed)

    def test_changes_still_goes_out_on_the_staged_head(self):
        # requesting changes on the reviewed commit approves nothing, and its comments are
        # pinned there, so a moved head is no reason to hold it back
        for move in self.MOVES:
            with self.subTest(move=move):
                gh, reviewed = self.staged_then_moved(move)
                out = gh.run("--pr", "5", "submit", "changes", "Summary.", check=False)
                self.assertEqual(out.returncode, 0, out.stderr)
                (review,) = gh.review_posts()
                self.assertEqual((review["event"], review["commit_id"]), ("REQUEST_CHANGES", reviewed))
                self.assertEqual([c["body"] for c in review["comments"]], ["Why change this?"])


class StagedQueueTest(MovedHeadCase):
    """There is always a way out of staged state: `discard` clears a PR's staged comments.

    Staged comments go stale when the PR head moves, and GitHub can reject a batch (422).
    Either way comment, suggest and submit refuse; each such refusal names `discard`, and
    after it the reviewer can stage and submit again.
    """

    # what gh prints when GitHub rejects the review, e.g. a comment off the diff
    REJECTED = ('gh: Unprocessable Entity (HTTP 422)\n{"message":"Unprocessable Entity","errors":'
                '["Pull request review thread line must be part of the diff"]}\n')

    def rejected(self):
        """(fake gh, reviewed head) after GitHub rejected the staged batch with a 422."""
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        gh.run("--pr", "5", "comment", "app.py:10", "Why change this?")
        gh.set_answer("POST /reviews", exit=1, stderr=self.REJECTED)
        return gh, self.repo.head

    def test_refusals_caused_by_staged_state_name_discard(self):
        for move in self.MOVES:
            for args in (("comment", "app.py:10", "More."), ("suggest", "app.py:10", "More."),
                         ("submit", "pass", "Summary.")):
                with self.subTest(move=move, verb=args[0]):
                    gh, _ = self.staged_then_moved(move)
                    out = gh.run("--pr", "5", *args, check=False, input_text="x = 1\n")
                    self.assertNotEqual(out.returncode, 0, f"{args[0]} went through: {out.stdout}")
                    self.assertIn("discard", out.stderr, "the refusal names the way out")
        with self.subTest("submit rejected by GitHub"):
            gh, _ = self.rejected()
            out = gh.run("--pr", "5", "submit", "changes", "Summary.", check=False)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("discard", out.stderr, "the refusal names the way out")

    def test_discard_clears_only_that_prs_staged_comments(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        gh = FakeGh(repo.path, {**pr_table(repo, 6), **pr_table(repo, 5)}, token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        for number in ("5", "6"):
            gh.run("--pr", number, "comment", "app.py:10", f"On PR {number}.")
        gh.run("--pr", "5", "discard")
        gh.run("--pr", "5", "submit", "pass", "Nothing left.")
        self.assertEqual(gh.review_posts()[-1].get("comments", []), [])
        gh.run("--pr", "6", "submit", "changes", "Still here.")
        self.assertEqual([c["body"] for c in gh.review_posts()[-1]["comments"]], ["On PR 6."])

    def test_after_discard_staging_and_submitting_work_again(self):
        cases = [(move, lambda move=move: self.staged_then_moved(move)) for move in self.MOVES]
        cases.append(("submit rejected by GitHub", self.rejected))
        for name, stuck in cases:
            with self.subTest(name):
                gh, _ = stuck()
                gh.run("--pr", "5", "submit", "pass", "S.", check=False)
                gh.run("--pr", "5", "discard")
                gh.set_answer("POST /reviews", json.dumps({"html_url": "https://github.com/o/r/pull/5"}))
                gh.run("--pr", "5", "comment", "app.py:10", "Fresh look.")
                gh.run("--pr", "5", "submit", "changes", "Again.")
                review = gh.review_posts()[-1]
                self.assertEqual(review["commit_id"], self.repo.head, "pinned on the current head")
                self.assertEqual([c["body"] for c in review["comments"]], ["Fresh look."])


class SuggestInputTest(unittest.TestCase):
    """suggest never posts a deletion by accident.

    The replacement comes from stdin or from --replacement, never both. An empty one is
    refused unless --delete asks for the deletion, and --delete takes no replacement. A
    bare `suggest a.py:3 "new code"` from a tool whose stdin is empty is the accident this
    prevents. Blank lines are a real replacement, not an empty one.
    """

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def gh(self):
        gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
        self.addCleanup(gh.cleanup)
        return gh

    def suggest(self, gh, *extra, stdin=""):
        return gh.run("--pr", "5", "suggest", "app.py:21-22", "Name these.", *extra,
                      check=False, input_text=stdin)

    def submitted(self, gh):
        gh.run("--pr", "5", "submit", "changes", "S.")
        return gh.review_posts()[-1].get("comments", [])

    def test_empty_replacement_is_refused_and_nothing_is_staged(self):
        for source, extra in [("stdin", ()), ("--replacement", ("--replacement", ""))]:
            with self.subTest(source):
                gh = self.gh()
                out = self.suggest(gh, *extra)
                self.assertNotEqual(out.returncode, 0, f"staged as a deletion: {out.stdout}")
                self.assertIn("--delete", out.stderr, "the refusal says how to ask for a deletion")
                self.assertEqual(self.submitted(gh), [], "nothing was staged")

    def test_blank_lines_are_a_real_replacement(self):
        cases = [("stdin", (), text, text) for text in ("\n", "\n\n", "  \n")] + \
                [("--replacement", ("--replacement", text), "", text) for text in ("\n", "\n\n")]
        for source, extra, stdin, want in cases:
            with self.subTest(source=source, replacement=want):
                gh = self.gh()
                out = self.suggest(gh, *extra, stdin=stdin)
                self.assertEqual(out.returncode, 0, out.stderr)
                (comment,) = self.submitted(gh)
                self.assertEqual(parse_suggestion(comment["body"]), want)

    def test_deletion_is_staged_when_asked_for(self):
        gh = self.gh()
        self.assertEqual(self.suggest(gh, "--delete").returncode, 0)
        (comment,) = self.submitted(gh)
        self.assertEqual(parse_suggestion(comment["body"]), "")
        self.assertEqual((comment.get("start_line"), comment["line"]), (21, 22))

    def test_replacement_can_come_from_an_argument(self):
        gh = self.gh()
        out = self.suggest(gh, "--replacement", "x = 1")
        self.assertEqual(out.returncode, 0, out.stderr)
        (comment,) = self.submitted(gh)
        self.assertEqual(parse_suggestion(comment["body"]), "x = 1\n")

    def test_two_answers_to_what_replaces_the_lines_are_refused(self):
        for name, extra, stdin in [
            ("--replacement and stdin", ("--replacement", "x = 1"), "y = 2\n"),
            ("--delete and stdin", ("--delete",), "y = 2\n"),
            ("--delete and blank lines on stdin", ("--delete",), "\n"),
            ("--delete and --replacement", ("--delete", "--replacement", "x = 1"), ""),
        ]:
            with self.subTest(name):
                gh = self.gh()
                out = self.suggest(gh, *extra, stdin=stdin)
                self.assertNotEqual(out.returncode, 0)
                self.assertRegex(out.stderr, r"(?i)pick one|not both|one or the other|only one"
                                             r"|not allowed with|mutually exclusive",
                                 "the refusal says to pick one")
                self.assertEqual(self.submitted(gh), [], "nothing was staged")


if __name__ == "__main__":
    unittest.main()
