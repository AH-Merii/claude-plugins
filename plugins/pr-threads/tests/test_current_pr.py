"""Without --pr, the PR comes from the current branch; when it can't, the user is told to pass it.

In a GitButler workspace the checked-out branch is always `gitbutler/workspace`, which has
no PR, and any other branch can have none either.
"""
import json
import os
import re
import unittest

from helpers import PLUGIN, FakeGh, Repo, git, pr_table, write_png


class NoPrForBranchTest(unittest.TestCase):
    """Every verb that works on "the current PR" stops before doing anything, naming --pr N."""

    BRANCHES = ["gitbutler/workspace", "no-pr-yet"]
    VERBS = [
        ("comment", "app.py:10", "Hmm.", "--attach", "shot.png"),
        ("suggest", "app.py:10", "Hmm.", "--attach", "shot.png"),
        ("submit", "changes", "Summary.", "--attach", "shot.png"),
        ("threads",),
        ("accept", "T1"),
        ("status",),
    ]

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        write_png(self.repo.path, "shot.png")

    def test_every_verb_refuses_and_asks_for_the_pr_number(self):
        for branch in self.BRANCHES:
            git(self.repo.path, "checkout", "-q", "-B", branch, self.repo.head)
            for args in self.VERBS:
                with self.subTest(branch=branch, verb=args[0]):
                    gh = FakeGh(self.repo.path, pr_table(self.repo), token="BOT_TOKEN")
                    self.addCleanup(gh.cleanup)
                    gh.set_answer("pr view", exit=1,
                                  stderr=f'no pull requests found for branch "{branch}"\n')
                    before = self.repo.read("app.py")
                    out = gh.run(*args, check=False, input_text="x = 1\n")
                    self.assertNotEqual(out.returncode, 0)
                    self.assertRegex(out.stderr, r"--pr\b", "the refusal says to pass --pr N")
                    self.assertEqual([c["route"] for c in gh.calls() if c["method"] == "POST"], [],
                                     "nothing was posted or queried")
                    self.assertEqual(gh.upload_calls(), [], "nothing was uploaded")
                    self.assertEqual(self.repo.read("app.py"), before)
                    # and nothing was staged for a later submit to send
                    gh.set_answer("pr view", stdout=json.dumps({
                        "number": 5, "baseRefOid": self.repo.base, "headRefOid": self.repo.head,
                        "headRefName": branch}))
                    gh.run("submit", "pass", "Nothing staged.", check=False)
                    self.assertEqual([r.get("comments", []) for r in gh.review_posts()], [[]])


class SkillTest(unittest.TestCase):
    def test_skill_says_to_pass_the_pr_number_in_a_gitbutler_workspace(self):
        with open(os.path.join(PLUGIN, "skills", "pr-threads", "SKILL.md")) as f:
            paragraphs = re.split(r"\n\s*\n", f.read())
        self.assertTrue([p for p in paragraphs if "--pr" in p and "gitbutler" in p.lower()],
                        "the skill tells the agent to pass --pr N where the branch has no PR")


if __name__ == "__main__":
    unittest.main()
