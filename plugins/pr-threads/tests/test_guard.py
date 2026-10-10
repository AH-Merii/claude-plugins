"""Guard hook: PR review and comment writes typed by an agent go through pr-threads instead."""
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
    "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T1\"}) { thread { id } } }'",
    "gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: \"T1\", body: \"ok\"}) { comment { id } } }'",
    "gh api graphql -f query='mutation($id: ID!) { addPullRequestReview(input: {pullRequestId: $id, event: COMMENT}) { pullRequestReview { id } } }'",
]

ALLOWED = [
    "gh pr view 5 --comments",
    "gh pr diff 5",
    "gh api repos/o/r/pulls/5/comments",
    "gh api repos/o/r/pulls/5/reviews --jq '.[].state'",
    "gh api -X GET repos/o/r/pulls/5/comments -f per_page=100",
    "gh api graphql -f query='query { repository(owner: \"o\", name: \"r\") { pullRequest(number: 5) { reviewThreads(first: 50) { nodes { id isResolved } } } } }'",
    "gh pr create --draft --title 'feat: x' --body 'y'",
    "gh pr edit 5 --body 'new description'",
    "gh issue create --title 'feat(x): y' --body 'z'",
    "but pr new my-branch -m 'feat: x'",
    "python3 -m pr_threads --pr 5 comment app.py:10 'why?'",
    "pr-threads --pr 5 resolve T1 T2",
    "echo 'gh pr comment 5 --body nope'",
    "git commit -m 'gh pr review 5 --approve'",
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
            ("gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread { id } } }'", "resolve"),
            ("gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: \"T\", body: \"x\"}) { comment { id } } }'", "reply"),
        ]:
            with self.subTest(command=command):
                self.assertIn("pr-threads", find_violation(command))
                self.assertIn(verb, find_violation(command))

    def test_unparseable_command_is_let_through(self):
        self.assertIsNone(find_violation("gh pr comment 5 --body 'unterminated"))


class HookProcessTest(unittest.TestCase):
    def run_hook(self, stdin):
        return subprocess.run([sys.executable, os.path.join(HOOKS, "pr_guard.py")],
                              input=stdin, capture_output=True, text=True)

    def test_denied_command_gets_a_deny_decision(self):
        out = self.run_hook(json.dumps({"tool_input": {"command": "gh pr review 5 --approve"}}))
        self.assertEqual(out.returncode, 0)
        decision = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]),
                         ("PreToolUse", "deny"))
        self.assertIn("pr-threads", decision["permissionDecisionReason"])

    def test_allowed_or_malformed_input_is_silent(self):
        for stdin in [json.dumps({"tool_input": {"command": "gh pr view 5"}}), "not json", ""]:
            with self.subTest(stdin=stdin):
                out = self.run_hook(stdin)
                self.assertEqual((out.returncode, out.stdout), (0, ""))


class HookRegistrationTest(unittest.TestCase):
    def test_hooks_json_runs_the_guard_before_bash(self):
        with open(os.path.join(HOOKS, "hooks.json")) as f:
            config = json.load(f)
        bash = [h for entry in config["hooks"]["PreToolUse"] if entry.get("matcher") == "Bash"
                for h in entry["hooks"]]
        self.assertTrue(any("pr_guard.py" in h["command"] for h in bash))
        for h in bash:
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", h["command"], "paths must not be absolute")


if __name__ == "__main__":
    unittest.main()
