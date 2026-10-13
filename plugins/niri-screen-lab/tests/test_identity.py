"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

The lab acts only on processes it started. Each lab's state.json, in its own folder, names every one of
them (the lab's Ghostty or Chromium, a recorder or poller, a browser lab's keeper) by pid and start time.
Once one has exited, the kernel may give its pid to another process, even one of the user's own Ghostty
or Chromium windows. No command, and no sweep of dead labs, may take that process for the lab's, or signal it.

These tests find the records by their shape ({"pid", "started"} anywhere in state.json), not by key.
"""

import json
import os
import shutil
import signal
import time
import unittest
from pathlib import Path

from labtest import DeskTest, sleeper, started, wait_for
from test_owner import LAB_ARGS

# Commands that act on a running lab, rather than stop it.
DRIVE = {name: argv for name, argv in LAB_ARGS.items() if name != "stop"}
# The ways a record can name a pid without naming the process now running under it.
NOT_THE_LAB = {
    "another start time": lambda rec, pid: rec.update(pid=pid),  # keeps the old process's start time
    "no start time": lambda rec, pid: (rec.update(pid=pid), rec.pop("started")),
}
KINDS = ("terminal", "browser")


def records(obj):
    """Every {"pid": int, "started": ...} record in a state file, as live references into it."""
    if isinstance(obj, dict):
        if isinstance(obj.get("pid"), int) and "started" in obj:
            yield obj
        for v in obj.values():
            yield from records(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from records(v)


def comm(pid):
    return Path(f"/proc/{pid}/comm").read_text().strip()


class IdentityTest(DeskTest):
    def open_recording(self, kind):
        """A lab of `kind` that is recording; its id and app pid."""
        lab_id = self.start() if kind == "terminal" else self.browse("--window", "about:blank")
        app = self.launch()["pid"]
        self.ok("rec-start", "--lab", lab_id)
        return lab_id, app

    def state(self, lab_id):
        path = self.state_dir(lab_id) / "state.json"
        return path, json.loads(path.read_text())

    def users_process(self, name):
        """A stand-in for one of the user's own processes, named like the lab's."""
        fake = self.tmp / name
        if not fake.exists():
            shutil.copy(shutil.which("sleep") or "/usr/bin/sleep", fake)
        p = sleeper(str(fake))
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        return p

    def hand_to_user(self, recs, how):
        """End each recorded process, then give its pid to a lookalike of the user's; returns the lookalikes."""
        users = []
        for rec in recs:
            pid, when = rec["pid"], rec["started"]
            name = comm(pid) if started(pid) == when else "ghostty"
            if pid > 1 and started(pid) == when:
                os.kill(pid, signal.SIGTERM)
            wait_for(lambda pid=pid, when=when: started(pid) != when, timeout=5, what=f"{name} to exit")
            user = self.users_process(name)
            NOT_THE_LAB[how](rec, user.pid)
            users.append(user)
        return users

    def stale_lab(self, kind, how):
        """A recording lab whose every recorded pid now belongs to one of the user's processes."""
        lab_id, _ = self.open_recording(kind)
        path, st = self.state(lab_id)
        recs = list(records(st))
        self.assertGreaterEqual(len(recs), 2 if kind == "terminal" else 3, f"too few process records: {st}")
        users = self.hand_to_user(recs, how)
        path.write_text(json.dumps(st))
        return lab_id, users

    def assertUntouched(self, users):
        time.sleep(0.05)  # a signal sent just now has been delivered by then
        for p in users:
            self.assertIsNone(p.poll(), f"signalled the user's {p.args[0]} (pid {p.pid})")

    def test_a_reused_pid_is_no_running_lab(self):
        for kind in KINDS:
            for how in NOT_THE_LAB:
                lab_id, users = self.stale_lab(kind, how)
                for command, argv in DRIVE.items():
                    with self.subTest(kind=kind, identity=how, command=command):
                        r = self.run_lab(*argv, "--lab", lab_id)
                        self.assertEqual(r.returncode, 1, r.stdout)
                        self.assertRegex(r.stderr, "(?i)no lab")
                        self.assertUntouched(users)

    def test_stop_and_the_sweep_signal_no_process_they_did_not_start(self):
        for kind in KINDS:
            for how in NOT_THE_LAB:
                for ender in (["stop", "--lab"], ["list"]):
                    with self.subTest(kind=kind, identity=how, command=ender[0]):
                        lab_id, users = self.stale_lab(kind, how)
                        self.run_lab(*ender, *([lab_id] if ender[0] == "stop" else []))
                        self.assertUntouched(users)
                        self.assertFalse(self.state_dir(lab_id).exists(), "the stale state was kept")

    def test_rec_stop_signals_no_recorder_it_did_not_start(self):
        for kind in KINDS:
            for how in NOT_THE_LAB:
                with self.subTest(kind=kind, identity=how):
                    lab_id, app = self.open_recording(kind)
                    path, st = self.state(lab_id)
                    helpers = [rec for rec in records(st) if rec["pid"] != app]
                    self.assertTrue(helpers, f"no recorder record: {st}")
                    users = self.hand_to_user(helpers, how)
                    path.write_text(json.dumps(st))
                    self.run_lab("rec-stop", str(self.tmp / "out.gif"), "--lab", lab_id)
                    self.assertUntouched(users)
                    self.ok("stop", "--lab", lab_id)

    def test_stop_ends_every_process_the_lab_started(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                lab_id, _ = self.open_recording(kind)
                _, st = self.state(lab_id)
                recs = [dict(r) for r in records(st)]
                self.assertGreaterEqual(len(recs), 2, f"too few process records: {st}")
                self.ok("stop", "--lab", lab_id)
                for rec in recs:
                    wait_for(lambda rec=rec: started(rec["pid"]) != rec["started"], timeout=5,
                             what=f"pid {rec['pid']} to exit")  # fmt: skip


if __name__ == "__main__":
    unittest.main()
