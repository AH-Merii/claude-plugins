"""Run with: python3 -m unittest discover -s plugins/gitbutler-guard/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "hooks")
sys.path.insert(0, HOOKS)

import git_guard  # noqa: E402
import skill_sync  # noqa: E402


def make_repo(root, branch):
    path = os.path.join(root, branch.replace("/", "-"))
    subprocess.run(["git", "init", "-q", "-b", branch, path], check=True)
    return path


class GitGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.workspace = make_repo(cls.tmp.name, "gitbutler/workspace")
        cls.plain = make_repo(cls.tmp.name, "main")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def blocked(self, command, cwd=None):
        hit = git_guard.find_violation(command, cwd or self.workspace)
        return hit[0] if hit else None

    def test_blocks_write_commands(self):
        for sub in ["add .", "commit -m 'x'", "push", "pull", "checkout -b x", "switch main",
                    "restore f", "reset --hard", "merge main", "rebase main", "stash",
                    "cherry-pick abc"]:
            with self.subTest(sub=sub):
                self.assertEqual(self.blocked(f"git {sub}"), sub.split()[0])

    def test_allows_read_only(self):
        for cmd in ["git status", "git log --oneline", "git diff", "git show HEAD",
                    "git blame f", "git stash list", "git branch", "git rev-parse HEAD",
                    'echo "git commit"', "but commit -b x -m y"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_finds_git_inside_compound_commands(self):
        self.assertEqual(self.blocked("ls && git add f"), "add")
        self.assertEqual(self.blocked("echo hi; git commit -m x"), "commit")
        self.assertEqual(self.blocked("echo hi\ngit push"), "push")
        self.assertEqual(self.blocked("(git stash)"), "stash")
        self.assertEqual(self.blocked("GIT_EDITOR=true git rebase main"), "rebase")
        self.assertEqual(self.blocked("sudo /usr/bin/git commit"), "commit")

    def test_skips_git_global_options(self):
        self.assertEqual(self.blocked("git -c user.name=x --no-pager commit -m x"), "commit")
        self.assertEqual(self.blocked(f"git -C {self.workspace} commit", cwd=self.plain), "commit")
        self.assertIsNone(self.blocked(f"git -C {self.plain} commit", cwd=self.workspace))

    def test_follows_cd(self):
        self.assertEqual(self.blocked(f"cd {self.workspace} && git commit", cwd=self.plain), "commit")
        self.assertIsNone(self.blocked(f"cd {self.plain} && git commit", cwd=self.workspace))

    def test_ignores_non_workspace_repos(self):
        self.assertIsNone(self.blocked("git commit -m x", cwd=self.plain))
        self.assertIsNone(self.blocked("git commit -m x", cwd=self.tmp.name))

    def test_multiline_quoted_message_is_one_command(self):
        self.assertEqual(self.blocked('git commit -m "line one\nline two"'), "commit")

    def test_hook_emits_deny_json(self):
        payload = json.dumps({"tool_input": {"command": "git commit -m x"}, "cwd": self.workspace})
        out = subprocess.run([sys.executable, os.path.join(HOOKS, "git_guard.py")],
                             input=payload, capture_output=True, text=True, check=True)
        decision = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("but commit", decision["permissionDecisionReason"])

    def test_hook_is_silent_when_allowed_or_malformed(self):
        for payload in [json.dumps({"tool_input": {"command": "git log"}, "cwd": self.workspace}),
                        "not json"]:
            out = subprocess.run([sys.executable, os.path.join(HOOKS, "git_guard.py")],
                                 input=payload, capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stdout), (0, ""))


class SkillSyncTest(unittest.TestCase):
    def test_reads_frontmatter_version(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write('---\nname: but\nversion: 0.22.3\ndescription: "x"\n---\n# body\nversion: 9\n')
        try:
            self.assertEqual(skill_sync.skill_version(f.name), "0.22.3")
        finally:
            os.unlink(f.name)

    def test_missing_skill_has_no_version(self):
        self.assertIsNone(skill_sync.skill_version("/nonexistent/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
