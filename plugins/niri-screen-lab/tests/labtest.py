"""DeskTest: runs lab.py as a child process against the fake desktop in fakedesk.py and fakebin.py.

Each test gets its own Desk, runtime dir, cache dir and niri config, and fake programs first on PATH.
After every test it checks the rules no command may break: no niri focus or screenshot action, no grim,
wf-recorder or busctl, and no DevTools call that raises or activates a target.
"""

import contextlib
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import fakebin
import fakedesk

SKILL = Path(__file__).resolve().parent.parent / "skills" / "niri-screen-lab"
LAB = str(SKILL / "lab.py")
SPARE = "eDP-1"
RULE = f"""
window-rule {{
    match app-id=r#"^dev\\.claude\\.lab$"#
    open-on-output "{SPARE}"
    open-focused false
}}
"""
ACTIVATION = {
    "XDG_ACTIVATION_TOKEN": "token-of-the-users-terminal",
    "DESKTOP_STARTUP_ID": "startup-of-the-users-terminal",
}
FORBIDDEN_CDP = {"Page.bringToFront", "Target.activateTarget"}


def started(pid):
    """Field 22 of /proc/PID/stat, or None once the process has exited."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return None
    return None if fields[0] in "ZX" else int(fields[19])


def sleeper(name="sleep"):
    return subprocess.Popen([name, "120"])


def wait_for(predicate, timeout=10.0, what="the condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


class DeskTest(unittest.TestCase):
    outputs = ("DP-1", SPARE)
    rule = True

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.desk = fakedesk.Desk(self.tmp / "niri.sock", self.outputs)
        self.addCleanup(self.desk.close)
        bin_dir, py_dir = self.tmp / "bin", self.tmp / "py"
        bin_dir.mkdir()
        fakebin.install(bin_dir, py_dir)
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.cache = self.tmp / "cache"
        config = self.tmp / "config.kdl"
        config.write_text(RULE if self.rule else "")
        drop = ("CLAUDE", "NIRI", "WAYLAND", "SCREEN_LAB", "XDG_", "TMUX")
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith(drop) and k not in ("DISPLAY", "PYTHONPATH")
        }
        self.env |= {
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "PYTHONPATH": str(py_dir),
            "NIRI_SOCKET": self.desk.path,
            "NIRI_CONFIG": str(config),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_CACHE_HOME": str(self.cache),
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
            **ACTIVATION,
        }
        self.addCleanup(self.assert_desktop_untouched)
        self.addCleanup(self.end_fakes)
        self.me = self.session()

    # ---------- sessions and commands ----------

    def session(self):
        """A stand-in for a Claude session: a live process whose pid is its CLAUDE_PID."""
        p = sleeper()
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        return p

    def run_lab(self, *args, session=None, timeout=60, unset=()):
        env = {**self.env, "CLAUDE_PID": str((session or self.me).pid)}
        env = {k: v for k, v in env.items() if k not in unset}
        return subprocess.run([sys.executable, LAB, *args], env=env, cwd=self.tmp, capture_output=True, text=True,
                              timeout=timeout, check=False)  # fmt: skip

    def ok(self, *args, session=None):
        r = self.run_lab(*args, session=session)
        self.assertEqual(r.returncode, 0, f"lab.py {' '.join(args)}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r

    def lab_id(self, r):
        m = re.search(r"^lab (\S+)$", r.stdout, re.MULTILINE)
        if m is None:
            self.fail(f"no `lab <id>` line in: {r.stdout!r}")
        return m.group(1)

    def start(self, *cmd, session=None):
        return self.lab_id(self.ok("start", "--", *(cmd or ("cat",)), session=session))

    def browse(self, *args, session=None):
        return self.lab_id(self.ok("browse", *(args or ("about:blank",)), session=session))

    def run_timed(self, *args, session=None):
        """Run lab.py, noting when each stderr line arrived: [(time, line)], with the CompletedProcess."""
        env = {**self.env, "CLAUDE_PID": str((session or self.me).pid)}
        p = subprocess.Popen([sys.executable, LAB, *args], env=env, cwd=self.tmp, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)  # fmt: skip
        lines, stdout, stderr = [], p.stdout, p.stderr
        assert stdout is not None and stderr is not None
        reader = threading.Thread(target=lambda: lines.extend((time.time(), line) for line in stderr))
        reader.start()
        out = stdout.read()
        p.wait(timeout=60)
        reader.join()
        return subprocess.CompletedProcess(p.args, p.returncode, out, "".join(t for _, t in lines)), lines

    # ---------- what the desktop shows ----------

    def workspace(self, lab):
        """The niri workspace named for lab `lab`, or None."""
        with self.desk.lock:
            return next((w for w in self.desk.workspaces_json() if w["name"] == f"claude-lab-{lab}"), None)

    def window(self, lab):
        """The window on lab `lab`'s workspace; fails unless there is exactly one."""
        ws = self.workspace(lab)
        self.assertIsNotNone(ws, f"no workspace named claude-lab-{lab}")
        with self.desk.lock:
            here = [w for w in self.desk.lab_windows() if w["workspace_id"] == ws["id"]]
        self.assertEqual(len(here), 1, f"windows on claude-lab-{lab}: {here}")
        return here[0]

    def launch(self, index=-1):
        """The index'th app launch the fakes saw: {"time", "app", "pid", "argv", "env"}."""
        return self.desk.launches[index]

    def actions(self, name):
        return [r["Action"][name] for _, r in self.desk.requests if isinstance(r, dict) and name in r.get("Action", {})]

    def cdp_calls(self, pid=None):
        return [m for _, p, m, _ in self.desk.cdp if pid is None or p == pid]

    def state_dir(self, lab):
        return self.runtime / "screen-lab" / lab

    def shape(self):
        with self.desk.lock:
            self.desk.reap()
            return self.desk.shape()

    # ---------- after every test ----------

    def end_fakes(self):
        for launch in self.desk.launches:
            pid = launch["pid"]
            if pid > 1 and started(pid) is not None:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGTERM)
        for launch in self.desk.launches:
            with contextlib.suppress(AssertionError):
                wait_for(lambda pid=launch["pid"]: started(pid) is None, timeout=3)

    def assert_desktop_untouched(self):
        self.assertEqual(self.desk.forbidden, [], "the lab sent niri a focus, screenshot or other forbidden action")
        ran = [t for t, _ in self.desk.ran if t in fakebin.FORBIDDEN_TOOLS]
        self.assertEqual(ran, [], "the lab ran a tool that captures the user's screen or bypasses gdbus")
        raised = [m for m in self.cdp_calls() if m in FORBIDDEN_CDP]
        self.assertEqual(raised, [], "the lab asked Chromium to raise or activate a target")


def png_size(path):
    w, h, _ = fakedesk.read_png(Path(path).read_bytes())
    return w, h
