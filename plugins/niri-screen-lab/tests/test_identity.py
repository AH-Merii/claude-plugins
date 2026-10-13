"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

The lab acts only on processes it started. state.json names each of them (the lab's Ghostty or
Chromium, the recorder, a browser lab's keeper) by pid and start time. Once one has exited, the
kernel may give its pid to another process, even one of the user's own Ghostty or Chromium
windows. No command may take that process for the lab's, or signal it.
"""

import contextlib
import shutil
import time
import unittest
from unittest import mock

from test_browser import LabStateTest
from test_owner import SAMPLE_ARGS, lab, lab_process, sleeper

APP = {"terminal": "ghostty", "browser": "chromium"}


def stale(kind, app, rec, keeper, video):
    """state.json naming three live processes by pid, with another process's start time."""

    def other(pid):
        return {"pid": pid, "started": 1}  # clock tick 1 after boot: never a process this test started

    return {"kind": kind, **other(app), "output": "eDP-1", "owner": None, "port": 9,
            "rec": {**other(rec), "video": video}, "keeper": other(keeper)}  # fmt: skip


def unverified(kind, app, rec, keeper, video):
    """state.json as lab.py wrote it before it recorded start times: bare pids."""
    return {"kind": kind, "pid": app, "output": "eDP-1", "owner": None, "port": 9,
            "rec": {"pid": rec, "video": video}, "keeper": keeper}  # fmt: skip


# The ways a state file can name a pid without naming the process now running under it.
NOT_THE_LAB = {"another start time": stale, "no start time": unverified}
# Commands that act on a running lab, rather than open or stop one.
DRIVE = {name: argv for name, argv in SAMPLE_ARGS.items() if name not in {"start", "browse", "stop"}}


class IdentityTest(LabStateTest):
    def setUp(self):
        super().setUp()
        self.users = set()  # pids of the stand-ins for the user's own processes
        # niri is the outside boundary. The user's window is found by its pid, as niri reports it.
        windows = {"workspaces": [{"id": 1, "output": "eDP-1", "is_active": True}], "windows": []}
        for name, fake in (
            ("niri", lambda *args: windows[args[0]]),
            ("find_window", lambda pid: self.user_window(pid)),
            ("need", lambda *_: None),  # grim, wf-recorder and ffmpeg may be missing; no test runs them
        ):
            patcher = mock.patch.object(lab, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.video = self.tmp / "rec.mp4"

    def user_window(self, pid):
        if pid not in self.users:
            return None
        return {"id": 7, "pid": pid, "app_id": "com.mitchellh.ghostty", "is_focused": False, "workspace_id": 2,
                "output": "DP-1", "layout": {"window_size": [100, 100]}}  # fmt: skip

    def spawn(self, name):
        """A long-lived process whose /proc/PID/comm reads `name`."""
        fake = self.tmp / name
        if not fake.exists():
            shutil.copy(shutil.which("sleep") or "/usr/bin/sleep", fake)
        p = sleeper(str(fake))
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        return p

    def users_process(self, name):
        """A stand-in for one of the user's own processes, named like the lab's."""
        p = self.spawn(name)
        self.users.add(p.pid)
        return p

    def stale_lab(self, kind, state, owner=None):
        """A state file whose lab, recorder and keeper pids now belong to the user's own processes."""
        app, rec, keeper = (self.users_process(n) for n in (APP[kind], "wf-recorder", "python3"))
        lab.save_state({**state(kind, app.pid, rec.pid, keeper.pid, str(self.video)), "owner": owner})
        return app, rec, keeper

    def assertUntouched(self, *procs):
        time.sleep(0.05)  # a signal sent just now has been delivered by then
        for p in procs:
            self.assertIsNone(p.poll(), f"signalled the user's {p.args[0]} (pid {p.pid})")

    def test_drive_commands_are_listed(self):
        self.assertIn("keys", DRIVE)
        self.assertNotIn("stop", DRIVE)

    def test_a_reused_pid_is_no_running_lab(self):
        for kind in APP:
            for how, state in NOT_THE_LAB.items():
                procs = self.stale_lab(kind, state)
                for command, argv in DRIVE.items():
                    with self.subTest(kind=kind, identity=how, command=command):
                        with self.assertRaisesRegex(lab.Refuse, "no lab is running"):
                            self.run_cmd(argv)
                        self.assertUntouched(*procs)

    def test_stop_signals_no_process_it_did_not_start(self):
        for kind in APP:
            for how, state in NOT_THE_LAB.items():
                with self.subTest(kind=kind, identity=how):
                    procs = self.stale_lab(kind, state)
                    self.run_cmd(["stop"])
                    self.assertUntouched(*procs)
                    self.assertIsNone(lab.load_state(), "the stale state was kept")

    def test_rec_stop_signals_no_recorder_it_did_not_start(self):
        for how, state in NOT_THE_LAB.items():
            with self.subTest(identity=how):
                self.video.touch()  # rec-stop deletes it
                app = self.spawn("ghostty")
                recorder = self.users_process("wf-recorder")
                st = state("terminal", app.pid, recorder.pid, None, str(self.video))
                lab.save_state({**st, **lab_process(app.pid)})
                with contextlib.suppress(lab.Refuse):
                    self.run_cmd(["rec-stop", str(self.tmp / "out.gif")])
                self.assertUntouched(recorder)

    def test_a_lab_whose_processes_exited_does_not_block_a_new_one(self):
        session = self.spawn("claude")  # another Claude session, still running
        for kind in APP:
            for how, state in NOT_THE_LAB.items():
                for owner in (None, session.pid):
                    with self.subTest(kind=kind, identity=how, owner=owner):
                        self.stale_lab(kind, state, owner)
                        lab.check_owner(lab.load_state())
                        lab.claim("eDP-1")

    def test_stop_ends_every_process_the_lab_started(self):
        for kind, name in APP.items():
            with self.subTest(kind=kind):
                app, recorder, keeper = (self.spawn(n) for n in (name, "wf-recorder", "python3"))
                rec = {**lab_process(recorder.pid), "video": str(self.video)}
                st = {"kind": kind, **lab_process(app.pid), "output": "eDP-1", "owner": None}
                lab.save_state({**st, "rec": rec, "keeper": lab_process(keeper.pid)})
                self.run_cmd(["stop"])
                for p in (app, recorder, keeper):
                    self.assertIsNotNone(p.wait(timeout=5), f"{p.args[0]} was left running")


if __name__ == "__main__":
    unittest.main()
