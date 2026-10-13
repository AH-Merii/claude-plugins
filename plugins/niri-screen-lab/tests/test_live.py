"""Contract with the real desktop: labs run side by side on hidden workspaces, and a headless browser lab drives a page.

Local only: needs niri, Ghostty, Chromium, GStreamer with vapostproc, a spare output with its window rule,
and gdbus. It opens lab windows on hidden workspaces of the spare output for a few seconds each.
Run with SCREEN_LAB_LIVE=1, outside a PID namespace (such as nm-sandbox): niri reports real pids, and a lab
matches its window by the pid it launched.
"""

import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from labtest import LAB, sleeper

APP_ID = "dev.claude.lab"
PAGE = (
    "data:text/html,<input id=i><button id=b style='width:200px;height:80px' "
    "onclick=\"document.title='clicked:'+document.getElementById('i').value\">go</button><input type=file id=f>"
)
TICKING = ["sh", "-c", "while :; do date +%T.%N; sleep 0.2; done"]


def niri(*args):
    return json.loads(subprocess.check_output(["niri", "msg", "--json", *args]))


def workspace_shape():
    """Each output's workspace names, in order: what the labs must leave as they found it."""
    shape = {}
    for w in sorted(niri("workspaces"), key=lambda w: (w["output"], w["idx"])):
        shape.setdefault(w["output"], []).append(w["name"])
    return shape


def niri_sees_our_pids():
    """Whether niri runs in this PID namespace: from another one, the socket reports its peer's pid as 0."""
    with socket.socket(socket.AF_UNIX) as s:
        s.connect(os.environ["NIRI_SOCKET"])
        pid, _, _ = struct.unpack("3i", s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    return pid > 0


@unittest.skipUnless(os.environ.get("SCREEN_LAB_LIVE") == "1", "set SCREEN_LAB_LIVE=1 to run")
class LiveTest(unittest.TestCase):
    def setUp(self):
        if not niri_sees_our_pids():
            self.skipTest("niri runs in another PID namespace, so its pids are not the ones the lab launched")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def session(self):
        p = sleeper()
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        return p

    def run_lab(self, session, *args):
        env = {**os.environ, "CLAUDE_PID": str(session.pid)}
        p = subprocess.run([sys.executable, LAB, *args], env=env, capture_output=True, text=True, timeout=90,
                           check=False)  # fmt: skip
        return p.returncode, p.stdout, p.stderr

    def ok(self, session, *args):
        rc, out, err = self.run_lab(session, *args)
        self.assertEqual(rc, 0, f"lab.py {' '.join(args)}: {err}")
        return out

    def open(self, session, *args):
        """Open a lab with `start ...` or `browse ...`; it is stopped when the test ends, whatever happens."""
        m = re.search(r"^lab (\S+)$", self.ok(session, *args), re.MULTILINE)
        if m is None:
            self.fail(f"{' '.join(args)} printed no `lab <id>` line")
        lab_id = m.group(1)
        self.addCleanup(self.run_lab, session, "stop", "--lab", lab_id)
        return lab_id

    def watch_events(self):
        """Every event niri sends from now until the test ends."""
        events = []
        p = subprocess.Popen(["niri", "msg", "--json", "event-stream"], stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.wait)
        self.addCleanup(p.terminate)
        out = p.stdout
        assert out is not None
        threading.Thread(target=lambda: events.extend(json.loads(line) for line in out), daemon=True).start()
        return events

    def test_parallel_labs_capture_without_focus_and_leave_the_workspaces_as_they_were(self):
        before = workspace_shape()
        events = self.watch_events()
        time.sleep(0.3)
        one, two = self.session(), self.session()
        labs = {
            "terminal 1": (one, self.open(one, "start", "--", *TICKING)),
            "terminal 2": (two, self.open(two, "start", "--", *TICKING)),
            "headless browser": (one, self.open(one, "browse", PAGE)),
            "windowed browser": (two, self.open(two, "browse", "--window", PAGE)),
        }
        for name, (session, lab_id) in labs.items():
            with self.subTest(lab=name):
                shot = self.tmp / f"{lab_id}.png"
                self.ok(session, "shot", str(shot), "--lab", lab_id)
                self.assertEqual(shot.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                self.assertGreater(shot.stat().st_size, 1000)
        session, lab_id = labs["terminal 1"]
        gif = self.tmp / "terminal.gif"
        self.ok(session, "gif", str(gif), "2", "--lab", lab_id)
        self.assertEqual(gif.read_bytes()[:6], b"GIF89a")
        for session, lab_id in labs.values():
            self.ok(session, "stop", "--lab", lab_id)
        time.sleep(0.5)

        opened = [e["WindowOpenedOrChanged"]["window"] for e in events if "WindowOpenedOrChanged" in e]
        lab_windows = {w["id"] for w in opened if w["app_id"] == APP_ID}
        self.assertGreaterEqual(len(lab_windows), 3, "the event stream missed the lab windows")
        focused = {w["id"] for w in opened if w["is_focused"]}
        focused |= {e["WindowFocusChanged"]["id"] for e in events if "WindowFocusChanged" in e}
        self.assertEqual(lab_windows & focused, set(), "a lab window had focus")
        self.assertEqual(niri("casts"), [], "a cast session outlived its lab")
        self.assertEqual(workspace_shape(), before)

    def test_a_headless_browser_lab_drives_a_page_and_cleans_up(self):
        me = self.session()
        lab_id = self.open(me, "browse", PAGE)
        state = Path(os.environ["XDG_RUNTIME_DIR"]) / "screen-lab" / lab_id
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "niri-screen-lab" / lab_id

        def js(expression):
            return json.loads(self.ok(me, "js", expression, "--lab", lab_id))

        js("document.getElementById('i').focus()")
        for args in (("keys", "hello"), ("key", "ctrl-a"), ("keys", "hi")):
            self.ok(me, *args, "--lab", lab_id)
        x, y = js(
            "(r => [r.x + r.width / 2, r.y + r.height / 2])(document.getElementById('b').getBoundingClientRect())"
        )
        self.ok(me, "click", str(round(x)), str(round(y)), "--lab", lab_id)
        self.assertEqual(js("document.title"), "clicked:hi")

        shot = self.tmp / "page.png"
        self.ok(me, "shot", str(shot), "--lab", lab_id)
        self.assertGreater(shot.stat().st_size, 1000)
        width, height = js("[innerWidth, innerHeight]")
        self.assertEqual(self.ok(me, "cell", str(width // 2), str(height // 2), "--lab", lab_id).split(),
                         [str(width // 2), str(height // 2)])  # fmt: skip

        x, y = js("(r => [r.x + 5, r.y + r.height / 2])(document.getElementById('f').getBoundingClientRect())")
        self.run_lab(me, "click", str(round(x)), str(round(y)), "--lab", lab_id)
        log = state / "filechooser.log"
        self.assertTrue(log.exists() and log.read_text().strip(), "the file chooser was not held back")
        info = json.loads(self.ok(me, "info", "--lab", lab_id))
        self.assertEqual([w for w in niri("windows") if w["pid"] == info["pid"]], [], "a headless lab has a window")

        self.ok(me, "stop", "--lab", lab_id)
        self.assertFalse(state.exists(), "the lab's state outlived it")
        self.assertFalse(cache.exists(), "the profile outlived the lab")


if __name__ == "__main__":
    unittest.main()
