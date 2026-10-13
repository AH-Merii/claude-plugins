"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

Several labs run at once, so every command that acts on a lab names it with `--lab ID`; there is no
"the only lab" default, since sibling subagents share CLAUDE_PID and could pick each other's lab.
A lab belongs to the Claude session that started it (CLAUDE_PID). While that session is alive, every
other session is refused, so parallel agents can't drive, capture or stop each other's lab. Once it has
ended, anyone may take the lab over.
"""

import argparse
import sys
import unittest
from pathlib import Path

from labtest import SKILL, DeskTest, started, wait_for

sys.path.insert(0, str(SKILL))

import lab

REFUSED = "another Claude session"

# One runnable argv per command that acts on a lab; `--lab ID` is added to each.
LAB_ARGS = {
    "open": ["open", "about:blank"],
    "js": ["js", "1"],
    "keys": ["keys", "x"],
    "key": ["key", "enter"],
    "hover": ["hover", "1", "1"],
    "click": ["click", "1", "1"],
    "scroll": ["scroll", "down", "1", "1"],
    "info": ["info"],
    "cell": ["cell", "1", "1"],
    "shot": ["shot", "out.png"],
    "gif": ["gif", "out.gif", "1"],
    "rec-start": ["rec-start"],
    "rec-stop": ["rec-stop", "out.gif"],
    "stop": ["stop"],
}
# Commands that take no lab id: they check the desktop, list the labs, or open a new one.
NO_LAB = {"preflight", "doctor", "list", "start", "browse"}


def commands():
    sub = next(a for a in lab.parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def on(lab_id, name):
    return [*LAB_ARGS[name], "--lab", lab_id]


class LabTest(DeskTest):
    def typed(self, lab_id, text):
        """True once lab `lab_id`'s terminal has printed `text`."""
        pid = self.window(lab_id)["pid"]
        return any(text in t for _, p, t in self.desk.draws if p == pid)


class LabAddressTest(LabTest):
    def test_every_command_is_classified(self):
        self.assertIn("keys", commands())
        self.assertEqual(commands(), set(LAB_ARGS) | NO_LAB)

    def test_every_lab_command_requires_lab_even_with_one_lab_running(self):
        only = self.start()
        for name, argv in LAB_ARGS.items():
            with self.subTest(command=name):
                r = self.run_lab(*(["keys", "no-default"] if name == "keys" else argv))
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("--lab", r.stderr)
        self.assertIsNotNone(started(self.window(only)["pid"]), "a command without --lab stopped the lab")
        self.assertFalse(self.typed(only, "no-default"), "keys without --lab reached the lab")

    def test_a_command_acts_only_on_the_lab_it_names(self):
        a, b = self.start(), self.start()
        self.ok("keys", "for-b", "--lab", b)
        wait_for(lambda: self.typed(b, "for-b"), what="lab b to print what was typed")
        self.assertFalse(self.typed(a, "for-b"))
        self.ok("stop", "--lab", a)
        self.assertIsNone(self.workspace(a))
        self.assertIsNotNone(started(self.window(b)["pid"]), "stopping lab a stopped lab b")

    def test_an_unknown_lab_is_refused(self):
        self.start()
        r = self.run_lab("keys", "x", "--lab", "no-such-lab")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no-such-lab", r.stderr)

    def test_each_lab_keeps_its_state_and_profile_in_its_own_folders(self):
        term, page = self.start(), self.browse()
        self.assertNotEqual(term, page)
        for lab_id in (term, page):
            self.assertTrue(self.state_dir(lab_id).is_dir(), f"no state folder for lab {lab_id}")
        chromium = next(x for x in self.desk.launches if x["app"] == "chromium")
        profile = next(a.split("=", 1)[1] for a in chromium["argv"] if a.startswith("--user-data-dir="))
        self.assertTrue(Path(profile).is_relative_to(self.cache / "niri-screen-lab" / page), profile)
        self.ok("stop", "--lab", term)
        self.assertFalse(self.state_dir(term).exists())
        self.assertTrue(self.state_dir(page).is_dir(), "stopping one lab removed another's state")


class OwnerTest(LabTest):
    def setUp(self):
        super().setUp()
        self.owner, self.other = self.session(), self.session()

    def test_another_live_session_is_refused_and_the_lab_is_untouched(self):
        lab_id = self.start(session=self.owner)
        pid = self.window(lab_id)["pid"]
        for name in LAB_ARGS:
            argv = ["keys", "from-other", "--lab", lab_id] if name == "keys" else on(lab_id, name)
            with self.subTest(command=name):
                r = self.run_lab(*argv, session=self.other)
                self.assertEqual(r.returncode, 1)
                self.assertIn(REFUSED, r.stderr)
                self.assertIsNotNone(started(pid), "the lab was stopped")
        self.assertFalse(self.typed(lab_id, "from-other"))

    def test_another_session_starts_its_own_lab_beside_a_running_one(self):
        mine = self.start(session=self.owner)
        theirs = self.start(session=self.other)
        self.assertNotEqual(mine, theirs)
        self.assertIsNotNone(started(self.window(mine)["pid"]))
        self.assertIsNotNone(started(self.window(theirs)["pid"]))

    def test_a_lab_whose_session_ended_can_be_taken_over(self):
        lab_id = self.start(session=self.owner)
        self.owner.kill()
        self.owner.wait()
        pid = self.window(lab_id)["pid"]
        for argv in (["list"], ["start", "--", "cat"], ["browse", "about:blank"]):  # each sweeps dead labs
            with self.subTest(command=argv[0]):
                self.ok(*argv, session=self.other)
                self.assertIsNotNone(started(pid), "the sweep ended a running lab because its session had ended")
                self.assertIn(lab_id, self.ok("list", session=self.other).stdout)
        self.ok("keys", "taken-over", "--lab", lab_id, session=self.other)
        wait_for(lambda: self.typed(lab_id, "taken-over"), what="the lab to print what was typed")


if __name__ == "__main__":
    unittest.main()
