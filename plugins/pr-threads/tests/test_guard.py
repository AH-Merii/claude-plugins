"""Guard hook: PR review and comment writes typed by an agent go through pr-threads instead.

Known gap: a GraphQL query read from a file (`-F query=@file`) can't be classified and goes through.
"""

import json
import os
import subprocess
import sys
import unittest

from helpers import PLUGIN

HOOKS = os.path.join(PLUGIN, "hooks")
sys.path.insert(0, HOOKS)

from pr_guard import find_violation  # noqa: E402

DENIED = [
    "gh pr comment 5 --body 'looks wrong'",
    "gh pr review 5 --approve",
    "gh pr review 5 --request-changes -b 'fix it'",
    "gh api repos/o/r/pulls/5/comments -f body=x -f path=a.py -F line=3",
    "gh api -X POST repos/o/r/pulls/5/reviews --input review.json",
    "gh api --method POST /repos/o/r/pulls/5/reviews/9/events -f event=APPROVE",
    "gh api repos/o/r/issues/5/comments -F body=@note.md",
    "gh api --method PATCH repos/o/r/pulls/comments/123 -f body=edited",
    "gh api -X DELETE repos/o/r/issues/comments/77",
    "gh issue comment 5 --body 'see above'",
    "gh issue comment 12 -F note.md",
    "/usr/bin/gh pr review 5 --approve",
    "env gh pr comment 5 -b x",
    'bash -c "gh pr comment 5 -b x"',
    "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T1\"}) { thread { id } } }'",
    'gh api graphql -f query=\'mutation { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: "T1", body: "ok"}) { comment { id } } }\'',
    "gh api graphql -f query='mutation($id: ID!) { addPullRequestReview(input: {pullRequestId: $id, event: COMMENT}) { pullRequestReview { id } } }'",
    'gh api graphql -f query=\'mutation { addComment(input: {subjectId: "PR_1", body: "x"}) { commentEdge { node { id } } } }\'',
    'gh api graphql -f query=\'mutation { addPullRequestReviewThread(input: {pullRequestReviewId: "R", path: "a.py", line: 3, body: "x"}) { thread { id } } }\'',
    "gh api graphql -f query='mutation { submitPullRequestReview(input: {pullRequestReviewId: \"R\", event: APPROVE}) { pullRequestReview { id } } }'",
    'gh api graphql -f query=\'mutation { updateIssueComment(input: {id: "IC_1", body: "x"}) { issueComment { id } } }\'',
    "gh api graphql -f query='mutation { deleteIssueComment(input: {id: \"IC_1\"}) { clientMutationId } }'",
    'gh api graphql -f query=\'mutation { addPullRequestReviewComment(input: {pullRequestReviewId: "R", path: "a.py", position: 3, body: "x"}) { comment { id } } }\'',
    'gh api graphql -f query=\'mutation { updatePullRequestReviewComment(input: {pullRequestReviewCommentId: "PRRC_1", body: "x"}) { pullRequestReviewComment { id } } }\'',
    "gh api graphql -f query='mutation { deletePullRequestReviewComment(input: {id: \"PRRC_1\"}) { clientMutationId } }'",
    'gh api graphql -f query=\'mutation { dismissPullRequestReview(input: {pullRequestReviewId: "R", message: "stale"}) { pullRequestReview { id } } }\'',
    "gh api graphql -f query='mutation { deletePullRequestReview(input: {pullRequestReviewId: \"R\"}) { pullRequestReview { id } } }'",
    # REST edits, dismissals and deletions of reviews and review comments
    "gh api -X PUT repos/o/r/pulls/5/reviews/9 -f body=edited",
    "gh api -X PUT repos/o/r/pulls/5/reviews/9/dismissals -f message=stale -f event=DISMISS",
    "gh api -X DELETE repos/o/r/pulls/5/reviews/9",
    "gh api -X DELETE repos/o/r/pulls/comments/123",
    # no body at all: only the method makes these writes (a bare POST opens a pending review)
    "gh api --method=POST repos/o/r/pulls/5/reviews",
    "gh api -XPOST repos/o/r/pulls/5/reviews",
    "gh api repos/o/r/pulls/5/comments/123/replies -f body=ok",
    # shlex can't split these (an odd quote), so only the raw text shows the write; a
    # parse failure must not wave them through
    "gh pr comment 5 --body-file - <<'EOF'\nit's broken\nEOF",
    "gh pr review 5 --approve -b 'it's fine'",
    "gh pr comment 5 --body 'unterminated",
    "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T1\"}) { thread { id } } }' && echo 'done",
]

ALLOWED = [
    "gh pr view 5 --comments",
    "gh pr diff 5",
    "gh api repos/o/r/pulls/5/comments",
    "gh api repos/o/r/pulls/5/reviews --jq '.[].state'",
    "gh api -X GET repos/o/r/pulls/5/comments -f per_page=100",
    "gh api -XGET repos/o/r/pulls/5/comments -f per_page=100",
    "gh api --method=GET repos/o/r/pulls/5/reviews -f per_page=100",
    "gh api repos/o/r/issues/5/comments",
    "gh api repos/o/r/issues/5/comments --jq '.[].body'",
    "gh api repos/o/r/pulls/5/reviews/9",
    "gh api repos/o/r/pulls/comments/123",
    'gh api graphql -f query=\'mutation { updatePullRequest(input: {pullRequestId: "P", title: "t"}) { pullRequest { id } } }\'',
    'gh api graphql -f query=\'query { repository(owner: "o", name: "r") { pullRequest(number: 5) { reviewThreads(first: 50) { nodes { id isResolved } } } } }\'',
    "gh pr create --draft --title 'feat: x' --body 'y'",
    "gh pr edit 5 --body 'new description'",
    "gh issue create --title 'feat(x): y' --body 'z'",
    "gh issue view 5 --comments",
    "gh issue list --state open",
    "but pr new my-branch -m 'feat: x'",
    "python3 -m pr_threads --pr 5 comment app.py:10 'why?'",
    "pr-threads --pr 5 resolve T1 T2",
    "echo 'gh pr comment 5 --body nope'",
    "git commit -m 'gh pr review 5 --approve'",
    # shlex can't split these either, but nothing in them is a PR write
    "echo 'it's fine'",
    "git commit -m \"don't stop",
    "cat <<'EOF'\nit's a note\nEOF",
]


class FindViolationTest(unittest.TestCase):
    def test_review_and_comment_writes_are_denied(self):
        for command in DENIED:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))

    def test_reads_and_unrelated_writes_are_allowed(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(find_violation(command))
                # and none of them hides a write on the line after it
                self.assertIsNotNone(find_violation(command + "\ngh pr comment 5 -b x"))

    def test_writes_are_found_inside_compound_commands(self):
        for command in [
            "cd repo && gh pr comment 5 -b x",
            "gh pr view 5; gh pr review 5 --approve",
            "GH_TOKEN=$(reviewer-token) gh api repos/o/r/pulls/5/reviews --input r.json",
            "(gh api repos/o/r/issues/5/comments -f body=x)",
            "true\ngh pr comment 5 -b x",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))

    def test_deny_names_the_pr_threads_command_to_use(self):
        for command, verb in [
            ("gh pr review 5 --approve", "submit"),
            (
                "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread { id } } }'",
                "resolve",
            ),
            (
                'gh api graphql -f query=\'mutation { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: "T", body: "x"}) { comment { id } } }\'',
                "reply",
            ),
            ("gh issue comment 5 --body x", "post"),
            ("gh api repos/o/r/issues/5/comments -f body=x", "post"),
            ("gh api repos/o/r/pulls/5/comments/123/replies -f body=x", "reply"),
        ]:
            with self.subTest(command=command):
                self.assertIn("pr-threads", find_violation(command))
                self.assertIn(verb, find_violation(command))


class DataIsNotCommandsTest(unittest.TestCase):
    """Text in a heredoc body or a quoted argument is data, not a command the shell runs.

    So mentions of PR writes there are allowed: notes, test corpora, suggested code. The
    command a heredoc belongs to, and every command after its closing line, is still checked.
    """

    HEREDOCS = [
        "cat > notes.md <<EOF\ngh pr comment 5 --body hi\nEOF",
        "cat > notes.md <<'EOF'\ngh api -X POST repos/o/r/pulls/1/comments -f body=x\nEOF",
        'cat > notes.md <<"END"\ngh issue comment 7 --body x\nEND',
        "cat <<-EOF > notes.md\n\tgh pr review 5 --approve\n\tEOF",
        "pr-threads --pr 5 suggest x.py:3 'Use this.' <<'EOF'\ngh api -X POST repos/o/r/pulls/1/comments\nEOF",
        "pr-threads --pr 5 suggest tests/test_guard.py:20 'Add a case.' <<'EOF'\n"
        '    "gh pr review 5 --approve",\n    "gh api graphql -f query=\'mutation { addComment }\'",\nEOF',
        # an odd quote in the body, which shlex can't split
        "cat > notes.md <<'EOF'\nit's gh pr comment 5 -b hi\nEOF",
        "cat > a.md <<A\ngh pr comment 1 -b x\nA\ncat > b.md <<B\ngh pr review 1 --approve\nB",
    ]
    QUOTED = [
        "pr-threads --pr 5 comment a.py:3 'Run this instead:\ngh pr comment 5 --body hi'",
        'pr-threads --pr 5 comment a.py:3 "Don\'t use\ngh api -X POST repos/o/r/pulls/1/reviews"',
        "gh pr create --title t --body 'Use gh pr comment 5 --body x, not gh api -X POST repos/o/r/pulls/5/reviews'",
        "git commit -m 'guard: deny\n\ngh pr review 5 --approve'",
    ]
    WRITE = "gh pr comment 5 -b x"

    def test_writes_mentioned_in_heredoc_bodies_and_quotes_are_allowed(self):
        for command in self.HEREDOCS + self.QUOTED:
            with self.subTest(command=command):
                self.assertIsNone(find_violation(command))

    def test_real_commands_around_the_data_are_still_denied(self):
        for command in self.HEREDOCS + self.QUOTED:
            with self.subTest(command=command, where="on the line after"):
                self.assertIsNotNone(find_violation(command + "\n" + self.WRITE))
        for command in [
            # on the heredoc's own line, after or before the redirection
            "cat > n.md <<EOF && gh pr comment 5 -b x\nhi\nEOF",
            "gh pr comment 5 --body-file - <<'EOF'\nhi\nEOF",
            # the body of a heredoc fed to a shell is commands
            "bash <<'EOF'\ngh pr comment 5 -b x\nEOF",
            "sh -s <<EOF\ngh pr review 5 --approve\nEOF",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))


class CommentsTest(unittest.TestCase):
    """#14: a `#` comment ends at the newline, and the next line is a command of its own.

    As in the shell, `#` starts a comment only at the start of a word and outside quotes, and
    the comment's own text is never a command. A word starts after whitespace and right after
    an operator: `bash -c 'echo a;# c; echo HIT'` prints only `a`. Any run of separators
    (`;`, `&&`, `|`, newlines, parentheses) splits commands, wherever a line ends.
    """

    # one write of each kind the guard denies; comments are handled once, in tokenize
    WRITES = [
        "gh pr comment 5 --body 'looks wrong'",
        "gh api -X POST repos/o/r/pulls/5/reviews --input review.json",
        "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T1\"}) { thread { id } } }'",
        # shlex can't split this, so the rough line-by-line check sees it
        "gh pr comment 5 --body 'unterminated",
    ]

    # a line ending in a comment, before the write on the next line
    COMMENTED = [
        "git push  # publish first",
        "cd repo # go there",
        "git fetch origin #sync",
        "git commit -qm wip # don't forget",
        "cd repo # go there\ngit status # check",
    ]

    def test_command_after_a_commented_line_is_checked(self):
        for line in self.COMMENTED:
            for command in self.WRITES:
                with self.subTest(line=line, command=command):
                    self.assertIsNotNone(find_violation(line + "\n" + command))

    def test_hash_inside_a_word_is_not_a_comment(self):
        for command in [
            "git checkout fix#12 && gh pr comment 12 -b done",
            "echo issue#5; gh pr review 5 --approve",
            "git log --grep=issue#5 | head; gh api repos/o/r/issues/5/comments -f body=x",
            # a length in bash, not a comment
            "echo ${#files[@]}; gh pr comment 5 -b x",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))

    def test_separators_ending_a_line_split_commands(self):
        for command in [
            "git push &&\ngh pr comment 5 -b x",
            "git push;\ngh pr comment 5 -b x",
            "git push |\ngh pr comment 5 -b x",
            "git push\n\ngh pr comment 5 -b x",
            "git push\n\n\ngh pr comment 5 -b x",
            "(cd x);gh pr comment 5 -b x",
            "(cd x)\ngh pr comment 5 -b x",
            "cd repo;# go there\ngh pr comment 5 -b x",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))

    # regression guards: the guard already gets these right

    def test_hash_right_after_an_operator_starts_a_comment(self):
        """Wrong fixes that start a comment only after whitespace fail these."""
        self.assertIsNotNone(find_violation("cd repo;# don't\ngh pr comment 5 -b x  # it's done"))
        for command in ["git push;# done; gh pr comment 5 -b x", "git push&&# then; gh pr review 5 --approve"]:
            with self.subTest(command=command):
                self.assertIsNone(find_violation(command))

    def test_hash_in_quotes_is_not_a_comment(self):
        for command in [
            "echo 'a # b'; gh pr comment 5 -b x",
            'gh pr comment 5 --body "fixes #5"',
            "git commit -m 'see #5' && gh pr review 5 --approve",
            # the write's body spans lines, so a wrongly stripped `#` can't fall back to the rough check
            "git commit -m 'refs #5' && gh pr comment 5 --body 'Fixed.\nThanks'",
            'git commit -m "refs #5" && gh pr comment 5 --body "Fixed.\nThanks"',
            # a quote in heredoc data opens nothing for the command lines after it
            "cat > body.md <<'EOF'\nIt's fixed: the cache is warmed first.\nEOF\n"
            "git commit -qam 'Fix #12' && gh pr comment 5 --body-file body.md",
            'cat > notes.md <<EOF\nUse a 6" pipe\nEOF\ngit commit -m "refs #5" && gh pr review 5 --approve',
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))

    def test_text_inside_a_comment_is_not_checked(self):
        for command in [
            "echo hi # gh pr comment 1",
            "# gh pr review 5 --approve",
            "git push # then gh api -X POST repos/o/r/issues/15/comments -f body=x",
            "cd repo # don't gh pr comment 5 -b x",
            "git push # done; gh pr comment 5 -b x",
            "git push\n# done; gh pr comment 5 -b x",
            "git push # publish first\ngh pr view 5 --comments",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(find_violation(command))

    def test_write_after_a_comment_only_line_is_denied(self):
        for command in ["# publish first\ngh pr comment 5 -b x", "cd repo; # go there\ngh pr comment 5 -b x"]:
            with self.subTest(command=command):
                self.assertIsNotNone(find_violation(command))


class HookProcessTest(unittest.TestCase):
    def run_hook(self, stdin):
        return subprocess.run(
            [sys.executable, os.path.join(HOOKS, "pr_guard.py")], input=stdin, capture_output=True, text=True
        )

    def test_denied_command_gets_a_deny_decision(self):
        out = self.run_hook(json.dumps({"tool_input": {"command": "gh pr review 5 --approve"}}))
        self.assertEqual(out.returncode, 0)
        decision = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("pr-threads", decision["permissionDecisionReason"])

    def test_allowed_or_malformed_input_is_silent(self):
        for stdin in [json.dumps({"tool_input": {"command": "gh pr view 5"}}), "not json", ""]:
            with self.subTest(stdin=stdin):
                out = self.run_hook(stdin)
                self.assertEqual((out.returncode, out.stdout), (0, ""))
        denied = self.run_hook(json.dumps({"tool_input": {"command": "gh pr comment 5 -b x"}}))
        self.assertIn("deny", denied.stdout, "the same hook does speak up for a write")


class HookRegistrationTest(unittest.TestCase):
    def test_hooks_json_runs_the_guard_before_bash(self):
        with open(os.path.join(HOOKS, "hooks.json")) as f:
            config = json.load(f)
        bash = [h for entry in config["hooks"]["PreToolUse"] if entry.get("matcher") == "Bash" for h in entry["hooks"]]
        self.assertTrue(any("pr_guard.py" in h["command"] for h in bash))
        for h in bash:
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", h["command"], "paths must not be absolute")


if __name__ == "__main__":
    unittest.main()
