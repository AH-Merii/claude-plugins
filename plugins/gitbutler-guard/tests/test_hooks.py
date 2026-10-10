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

    def advice(self, command):
        return git_guard.find_violation(command, self.workspace)[1]

    def test_blocks_branch_writes(self):
        for cmd in ["git branch x", "git branch x HEAD~1", "git branch -d x", "git branch -D x",
                    "git branch --delete x", "git branch -dr origin/x", "git branch -m x y",
                    "git branch -M y", "git branch --move x y", "git branch -c x y",
                    "git branch -f x HEAD~1", "git branch --force x", "git branch -u origin/x",
                    "git branch --set-upstream-to=origin/x", "git branch --unset-upstream",
                    "git branch --edit-description", "git branch -v --delete x",
                    f"cd {self.plain} && env GIT_TRACE=0 git -C {self.workspace} branch -D x"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "branch")
        self.assertIn("but branch new", self.advice("git branch x"))
        self.assertIn("but branch delete", self.advice("git branch -D x"))
        self.assertIn("but reword", self.advice("git branch -m x y"))

    def test_allows_branch_listing(self):
        for cmd in ["git branch", "git branch -a", "git branch -r", "git branch -vv",
                    "git branch --show-current", "git branch --list x", "git branch -l 'feat/*'",
                    "git branch --contains", "git branch --contains abc", "git branch --no-merged main",
                    "git branch --points-at HEAD", "git branch --sort -committerdate",
                    "git branch --format '%(refname)'", "git -c color.ui=never branch -a"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_blocks_tag_writes(self):
        for cmd in ["git tag v1", "git tag v1 HEAD~1", "git tag -a v1 -m msg", "git tag -s v1",
                    "git tag -f v1", "git tag -d v1", "git tag --delete v1", "git tag -m msg v1",
                    "git -c tag.gpgSign=false tag v1"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "tag")
        self.assertIn("no tag command", self.advice("git tag v1"))

    def test_allows_tag_listing(self):
        for cmd in ["git tag", "git tag -l", "git tag -l 'v1.*'", "git tag --list", "git tag -n",
                    "git tag -n3", "git tag --contains HEAD", "git tag --points-at HEAD",
                    "git tag --merged main", "git tag --sort=-v:refname",
                    "git tag --sort -creatordate", "git tag -v v1"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_blocks_rm(self):
        for cmd in ["git rm f", "git rm -r dir", "git rm --cached f", "git rm -f f", "git rm -- -n",
                    "sudo git --no-pager rm f"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "rm")
        self.assertIn("plain `rm <path>`", self.advice("git rm f"))

    def test_allows_rm_dry_run(self):
        for cmd in ["git rm -n f", "git rm --dry-run -r dir", "git rm -rn dir"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_blocks_mv(self):
        for cmd in ["git mv a b", "git mv -f a b", "git mv -k a b dir",
                    "GIT_DIR=.git command git mv a b"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "mv")
        self.assertIn("plain `mv <old> <new>`", self.advice("git mv a b"))

    def test_allows_mv_dry_run(self):
        for cmd in ["git mv -n a b", "git mv --dry-run a b"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_blocks_clean(self):
        for cmd in ["git clean -f", "git clean -fd", "git clean -fdx", "git clean --force -d",
                    "git clean -i", "git clean -f -e n", "git --work-tree=. clean -fdx"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "clean")
        self.assertIn("but discard", self.advice("git clean -fd"))

    def test_allows_clean_dry_run(self):
        for cmd in ["git clean -n", "git clean -fdn", "git clean --dry-run -d", "git clean -nd -e build"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.blocked(cmd))

    def test_blocks_update_ref(self):
        for cmd in ["git update-ref refs/heads/x HEAD", "git update-ref -d refs/heads/x",
                    "git update-ref --stdin", "git update-ref -m msg HEAD abc"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "update-ref")
        self.assertEqual(self.blocked(f"exec git -C {self.workspace} update-ref HEAD abc",
                                      cwd=self.plain), "update-ref")
        self.assertIn("no update-ref command", self.advice("git update-ref HEAD abc"))

    def test_blocks_notes_writes(self):
        for cmd in ["git notes add -m x", "git notes append -m x HEAD", "git notes copy a b",
                    "git notes edit", "git notes merge other", "git notes remove HEAD",
                    "git notes prune", "git notes --ref review add -m x HEAD",
                    "time git -c core.editor=true notes edit"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.blocked(cmd), "notes")
        self.assertIn("no notes command", self.advice("git notes add -m x"))

    def test_allows_notes_reads(self):
        for cmd in ["git notes", "git notes list", "git notes show HEAD", "git notes get-ref",
                    "git notes --ref review show", "git notes --ref=review list"]:
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
