"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

A lab belongs to the Claude session that started it (CLAUDE_PID). While that session
is alive, every other session is refused, so parallel agents can't drive, capture or
stop each other's lab. Once it has ended, anyone may take the lab over.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = os.path.join(os.path.dirname(__file__), "..", "skills", "niri-screen-lab")
LAB = os.path.join(SKILL, "lab.py")
sys.path.insert(0, SKILL)

import lab

REFUSED = "another Claude session"

# One runnable argv per command that touches the lab.
SAMPLE_ARGS = {
    "start": ["start", "--", "true"],
    "browse": ["browse", "about:blank"],
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
# Commands that never touch a running lab.
LAB_FREE = {"preflight", "doctor"}


def commands():
    sub = next(a for a in lab.parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def lab_process(pid):
    """A process as lab.py records one it started: its pid and start time (field 22 of /proc/PID/stat)."""
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "started": int(fields[19])}


def sleeper(name="sleep"):
    """A long-lived process; `name` sets what /proc/PID/comm reads."""
    return subprocess.Popen([name, "60"])


class OwnerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.state = os.path.join(self.tmp, "screen-lab")
        os.mkdir(self.state, 0o700)
        # Stand-in for the lab's Ghostty, recorded as the process the lab started.
        fake = os.path.join(self.tmp, "ghostty")
        shutil.copy(shutil.which("sleep") or "/usr/bin/sleep", fake)
        self.ghostty = self.spawn(fake)
        self.owner = self.spawn()
        self.other = self.spawn()
        # The relay's side of the input FIFO.
        feed = os.path.join(self.state, "feed")
        os.mkfifo(feed, 0o600)
        self.feed = os.open(feed, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, self.feed)

    def spawn(self, name="sleep"):
        p = sleeper(name)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        return p

    def make_lab(self, owner):
        with open(os.path.join(self.state, "state.json"), "w") as f:
            json.dump(
                {
                    **lab_process(self.ghostty.pid),
                    "output": "eDP-1",
                    "app_id": lab.APP_ID,
                    "cmd": ["true"],
                    "owner": owner,
                },
                f,
            )

    def run_lab(self, args, session):
        env = {
            k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "NIRI", "WAYLAND")) and k != "DISPLAY"
        }
        env |= {"XDG_RUNTIME_DIR": self.tmp, "CLAUDE_PID": str(session.pid)}
        return subprocess.run(
            [sys.executable, LAB, *args], env=env, cwd=self.tmp, capture_output=True, text=True, timeout=30, check=False
        )

    def fed(self):
        try:
            return os.read(self.feed, 4096)
        except BlockingIOError:
            return b""

    def test_every_command_is_classified(self):
        self.assertIn("keys", commands())
        self.assertEqual(commands(), set(SAMPLE_ARGS) | LAB_FREE)

    def test_the_owning_session_drives_its_lab(self):
        self.make_lab(self.owner.pid)
        r = self.run_lab(["keys", "hi"], self.owner)
        self.assertEqual(self.fed(), b"hi", r.stderr)

    def test_another_live_session_is_refused_and_the_lab_is_untouched(self):
        self.make_lab(self.owner.pid)
        for name, args in SAMPLE_ARGS.items():
            with self.subTest(command=name):
                r = self.run_lab(args, self.other)
                self.assertIn(REFUSED, r.stderr)
                self.assertNotIn("lab.py stop", r.stderr)
                self.assertIsNone(self.ghostty.poll(), "the lab was killed")
                self.assertEqual(self.fed(), b"")

    def test_a_lab_whose_session_ended_can_be_taken_over(self):
        ended = subprocess.Popen(["true"])
        ended.wait()
        self.make_lab(ended.pid)
        r = self.run_lab(["keys", "hi"], self.other)
        self.assertEqual(self.fed(), b"hi", r.stderr)


if __name__ == "__main__":
    unittest.main()
