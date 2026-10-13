"""Contract with the real desktop: two sessions start a lab at the same moment, and a browser lab drives a page.

Local only: needs niri, Ghostty, Chromium, a spare output with its window rule, and no lab running.
It opens lab windows on the spare output for a few seconds each. Run with SCREEN_LAB_LIVE=1.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_owner import LAB, REFUSED, lab, sleeper

PAGE = (
    "data:text/html,<input id=i><button id=b style='width:200px;height:80px' "
    "onclick=\"document.title='clicked:'+document.getElementById('i').value\">go</button><input type=file id=f>"
)


def close(pid):
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)


@unittest.skipUnless(os.environ.get("SCREEN_LAB_LIVE") == "1", "set SCREEN_LAB_LIVE=1 to run")
class LiveTest(unittest.TestCase):
    def lab(self, session, *args):
        env = {**os.environ, "CLAUDE_PID": str(session.pid)}
        return subprocess.Popen(
            [sys.executable, LAB, *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    def run_lab(self, session, *args):
        p = self.lab(session, *args)
        out, err = p.communicate(timeout=60)
        return p.returncode, out, err

    def test_one_of_two_simultaneous_starts_wins_and_keeps_the_lab(self):
        a, b = sleeper(), sleeper()
        for p in (a, b):
            self.addCleanup(p.wait)
            self.addCleanup(p.kill)
        starts = {s: self.lab(s, "start", "--", "sleep", "30") for s in (a, b)}
        results = {s: (p.wait(timeout=60), *p.communicate()) for s, p in starts.items()}
        for rc, out, _ in results.values():
            if rc == 0:
                # Close every lab this test opened, even when two of them got through.
                self.addCleanup(close, json.loads(out)["pid"])
        winners = [s for s, (rc, _, _) in results.items() if rc == 0]
        self.assertEqual(len(winners), 1, results)
        winner = winners[0]
        loser = b if winner is a else a
        self.addCleanup(self.run_lab, winner, "stop")
        self.assertIn(REFUSED, results[loser][2])

        for args in (("keys", "x"), ("stop",)):
            with self.subTest(command=args[0]):
                rc, _, err = self.run_lab(loser, *args)
                self.assertNotEqual(rc, 0)
                self.assertIn(REFUSED, err)
        rc, out, err = self.run_lab(winner, "stop")
        self.assertEqual((rc, out.strip()), (0, "stopped"), err)

    def test_a_browser_lab_drives_a_page_without_focus_and_cleans_up(self):
        me = sleeper()
        self.addCleanup(me.wait)
        self.addCleanup(me.kill)
        rc, out, err = self.run_lab(me, "browse", PAGE)
        self.assertEqual(rc, 0, err)
        self.addCleanup(close, json.loads(out)["pid"])
        self.addCleanup(self.run_lab, me, "stop")
        state = Path(os.environ["XDG_RUNTIME_DIR"]) / "screen-lab"

        def js(expression):
            rc, out, err = self.run_lab(me, "js", expression)
            self.assertEqual(rc, 0, err)
            return json.loads(out)

        js("document.getElementById('i').focus()")
        for args in (("keys", "hello"), ("key", "ctrl-a"), ("keys", "hi")):
            self.assertEqual(self.run_lab(me, *args)[0], 0, args)
        x, y = js(
            "(r => [r.x + r.width / 2, r.y + r.height / 2])(document.getElementById('b').getBoundingClientRect())"
        )
        self.assertEqual(self.run_lab(me, "click", str(round(x)), str(round(y)))[0], 0)
        self.assertEqual(js("document.title"), "clicked:hi")

        with tempfile.TemporaryDirectory() as tmp:
            shot = Path(tmp) / "page.png"
            rc, _, err = self.run_lab(me, "shot", str(shot), "--crop")
            self.assertEqual(rc, 0, err)
            self.assertGreater(shot.stat().st_size, 1000)
        info = json.loads(self.run_lab(me, "info")[1])
        v = info["viewport"]
        rc, out, err = self.run_lab(me, "cell", str(v["x"] + v["width"] / 2), str(v["y"] + v["height"] / 2))
        self.assertEqual(out.split(), [str(round(v["css_width"] / 2)), str(round(v["css_height"] / 2))], err)

        x, y = js("(r => [r.x + 5, r.y + r.height / 2])(document.getElementById('f').getBoundingClientRect())")
        self.run_lab(me, "click", str(round(x)), str(round(y)))
        log = state / "filechooser.log"
        self.assertTrue(log.exists() and log.read_text().strip(), "the file chooser was not held back")
        windows = [w for w in lab.niri("windows") if w["pid"] == info["pid"]]
        self.assertEqual(len(windows), 1, "a dialog window opened")
        self.assertFalse(windows[0]["is_focused"])

        rc, out, err = self.run_lab(me, "stop")
        self.assertEqual((rc, out.strip()), (0, "stopped"), err)
        self.assertFalse((lab.CACHE / "profile").exists(), "the profile outlived the lab")


if __name__ == "__main__":
    unittest.main()
