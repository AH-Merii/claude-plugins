"""Contract with the real desktop: two sessions start a lab at the same moment.

Local only: needs niri, Ghostty, a spare output with its window rule, and no lab running.
It opens the lab window on the spare output for a few seconds. Run with SCREEN_LAB_LIVE=1.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import unittest

from test_owner import LAB, REFUSED, sleeper


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


if __name__ == "__main__":
    unittest.main()
