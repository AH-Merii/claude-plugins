"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

Where lab windows go, and how labs end. Every windowed lab lives on its own hidden niri workspace,
`claude-lab-<id>`, on the chosen output: the lab listens to niri's event stream before it launches, then
moves its window to that output's trailing workspace by id, names it, and checks the result, closing the
window and refusing on any failure. With two screens niri's window rule must send the lab to the spare
one; on a single screen no rule is needed, and the user is warned about a 50 ms focus flash. Browser labs
are headless unless `--window`. `stop` and the sweep of dead labs leave the workspaces as they were.
"""

import os
import re
import signal
import threading
import unittest
from pathlib import Path

from labtest import ACTIVATION, SPARE, DeskTest, started, wait_for

FLASH = "holds keyboard focus for about 50 ms"


def meminfo_mib():
    m = re.search(r"^MemAvailable:\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.MULTILINE)
    if m is None:
        raise unittest.SkipTest("/proc/meminfo has no MemAvailable")
    return int(m.group(1)) // 1024


class PlacementTest(DeskTest):
    def test_a_lab_window_lands_unfocused_on_its_own_hidden_workspace(self):
        lab_id = self.start()
        w, ws = self.window(lab_id), self.workspace(lab_id)
        self.assertEqual(ws["output"], SPARE)
        self.assertFalse(ws["is_active"], "the lab's workspace is the visible one")
        self.assertFalse(w["is_focused"])
        self.assertEqual(self.desk.focus, 1, "the user's window lost focus")
        spare = [x for x in self.desk.workspaces_json() if x["output"] == SPARE]
        self.assertEqual((spare[-1]["name"], spare[-1]["active_window_id"]), (None, None),
                         "the spare output no longer ends in an empty workspace")  # fmt: skip
        visible = next(x for x in spare if x["is_active"])
        self.assertEqual(visible["active_window_id"], 2, "the user's own window left the visible spare workspace")

    def test_multi_screen_labs_give_no_focus_warning(self):
        r = self.ok("start", "--", "cat")
        self.window(self.lab_id(r))
        self.assertNotIn(FLASH, r.stderr)

    def test_a_lab_places_its_own_window_not_another_labs(self):
        a = self.start()
        first = self.window(a)
        b = self.start()  # while it launches, lab a's window reports a change (fakedesk.py)
        self.assertEqual(self.window(b)["pid"], self.launch()["pid"])
        self.assertEqual((self.window(a)["id"], self.window(a)["workspace_id"]), (first["id"], first["workspace_id"]))

    def test_labs_started_at_once_each_get_a_workspace_of_their_own(self):
        with self.desk.lock:
            self.desk.pair_workspaces = 0.5  # both labs read the same layout unless placement is serialised
        runs = {}
        threads = [threading.Thread(target=lambda i=i: runs.__setitem__(i, self.run_lab("start", "--", "cat")))
                   for i in range(2)]  # fmt: skip
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for r in runs.values():
            self.assertEqual(r.returncode, 0, r.stderr)
        a, b = (self.lab_id(r) for r in runs.values())
        self.assertNotEqual(a, b)
        self.assertNotEqual(self.window(a)["id"], self.window(b)["id"])

    def test_the_lab_listens_to_niri_before_it_launches(self):
        for argv in (["start", "--", "cat"], ["browse", "--window", "about:blank"]):
            with self.subTest(command=argv[0]):
                self.ok(*argv)
                launch = self.launch()
                lab = launch["line"][launch["line"].index(os.getpid()) - 1]  # the lab.py run that launched it
                streams = [s for s in self.desk.streams_opened if lab in s["line"]]
                self.assertTrue(streams, "the lab never opened niri's event stream")
                self.assertTrue(any(launch["pid"] not in s["alive"] for s in streams),
                                "the lab launched its app before niri had answered its event stream")  # fmt: skip

    def test_the_window_is_moved_then_its_workspace_named_both_by_a_fresh_id(self):
        before = {w["id"] for w in self.desk.workspaces_json()}
        lab_id = self.start()
        w, ws = self.window(lab_id), self.workspace(lab_id)
        order = [
            (i, r["Action"]) for i, (_, r) in enumerate(self.desk.requests) if isinstance(r, dict) and "Action" in r
        ]
        moves = [i for i, a in order if a.get("MoveWindowToWorkspace", {}).get("window_id") == w["id"]]
        names = [i for i, a in order if a.get("SetWorkspaceName", {}).get("name") == f"claude-lab-{lab_id}"]
        self.assertTrue(moves and names, order)
        self.assertLess(moves[0], names[0], "the workspace was named before the window moved onto it")
        move, name = dict(order)[moves[0]]["MoveWindowToWorkspace"], dict(order)[names[0]]["SetWorkspaceName"]
        self.assertEqual((move["reference"], move["focus"]), ({"Id": ws["id"]}, False))
        self.assertEqual(name["workspace"], {"Id": ws["id"]})
        self.assertNotIn(ws["id"], before, "the lab used a workspace id read before its window opened")

    def test_a_failed_placement_closes_the_window_unnames_the_workspace_and_refuses(self):
        failures = {
            "the move did nothing": lambda d: d.ignore.add("MoveWindowToWorkspace"),
            "the naming did nothing": lambda d: d.ignore.add("SetWorkspaceName"),
            "the window took focus": lambda d: setattr(d, "focus_on_move", True),
        }
        for how, breaks in failures.items():
            with self.subTest(failure=how):
                with self.desk.lock:
                    breaks(self.desk)
                opened = len(self.desk.opened)
                r = self.run_lab("start", "--", "cat")
                with self.desk.lock:
                    self.desk.ignore.clear()
                    self.desk.focus_on_move = False
                self.assertEqual(len(self.desk.opened), opened + 1, f"no lab window opened: {r.stderr}")
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(r.stderr.strip())
                wait_for(lambda: self.shape() == self.desk.start_shape, timeout=10,
                         what="the window closed and the workspaces back as they were")  # fmt: skip
                self.assertEqual(self.desk.focus, 1)
                left = [p.name for p in (self.runtime / "screen-lab").glob("*") if p.is_dir()]
                self.assertEqual(left, [], "the refused lab left its state behind")


class TwoScreensWithoutRuleTest(DeskTest):
    rule = False

    def test_a_window_is_refused_before_launch_and_the_rule_is_shown(self):
        for argv in (["start", "--", "cat"], ["browse", "--window", "about:blank"]):
            with self.subTest(command=argv[0]):
                r = self.run_lab(*argv)
                self.assertEqual(r.returncode, 1)
                self.assertIn("window-rule", r.stderr)
        self.assertEqual(self.desk.launches, [], "a lab was launched without the rule")

    def test_a_headless_browser_needs_no_rule(self):
        self.browse()


class SingleScreenTest(DeskTest):
    outputs = ("DP-1",)
    rule = False

    def test_the_only_screen_hosts_hidden_labs_after_a_warning(self):
        r, lines = self.run_timed("start", "--", "cat")
        self.assertEqual(r.returncode, 0, r.stderr)
        warned = [t for t, line in lines if FLASH in line]
        self.assertTrue(warned, r.stderr)
        self.assertLess(warned[0], self.launch()["time"], "the warning came after the launch")
        lab_id = self.lab_id(r)
        ws = self.workspace(lab_id)
        self.assertEqual(ws["output"], "DP-1")
        self.assertFalse(ws["is_active"])
        self.assertFalse(self.window(lab_id)["is_focused"])
        self.assertEqual(self.desk.focus, 1, "focus did not go back to the user's window")


class HeadlessTest(DeskTest):
    def test_browse_is_headless_by_default_with_no_window_or_workspace(self):
        lab_id = self.browse()
        self.assertIn("--headless=new", self.launch()["argv"])
        self.assertEqual(self.desk.lab_windows(), [])
        self.assertIsNone(self.workspace(lab_id))
        self.assertEqual(self.actions("MoveWindowToWorkspace") + self.actions("SetWorkspaceName"), [])

    def test_browse_window_opens_a_placed_window(self):
        lab_id = self.browse("--window", "about:blank")
        self.assertFalse([a for a in self.launch()["argv"] if a.startswith("--headless")])
        self.assertFalse(self.window(lab_id)["is_focused"])
        self.assertEqual(self.workspace(lab_id)["output"], SPARE)

    def test_a_headless_lab_opens_at_a_desktop_size(self):
        # Chromium's headless default gave a 780x493 viewport live: most sites lay that out as a tablet.
        self.browse()
        self.assertIn("--window-size=1280,800", self.launch()["argv"])

    def test_chromium_keeps_its_temporary_files_in_the_labs_own_folder(self):
        # A long TMPDIR made Chromium's singleton socket path too long to bind, and a stopped lab left its
        # org.chromium.Chromium.* folders behind in TMPDIR.
        self.env["TMPDIR"] = str(self.tmp / ("long-" * 20))
        for args in ((), ("--window", "about:blank")):
            with self.subTest(args=args):
                lab_id = self.browse(*args)
                tmp = Path(self.launch()["env"].get("TMPDIR", ""))
                self.assertTrue(tmp.is_relative_to(self.state_dir(lab_id)), tmp)
                self.assertTrue(tmp.is_dir(), tmp)


class LaunchTest(DeskTest):
    def test_lab_apps_get_no_activation_token_or_session_variables(self):
        self.start()
        self.browse()
        self.browse("--window", "about:blank")
        self.assertEqual([x["app"] for x in self.desk.launches], ["ghostty", "chromium", "chromium"])
        for launch in self.desk.launches:
            with self.subTest(app=launch["app"], argv=launch["argv"][-1]):
                leaked = {k for k in launch["env"] if k in ACTIVATION or k == "CLAUDE_PID"}
                self.assertEqual(leaked, set())

    def test_ghostty_runs_its_own_instance_without_desktop_notifications(self):
        self.start()
        argv = self.launch()["argv"]
        self.assertIn("--gtk-single-instance=false", argv)
        self.assertIn("--desktop-notifications=false", argv)

    def test_preflight_start_and_browse_print_the_memory_available(self):
        for argv in (["preflight"], ["start", "--", "cat"], ["browse", "about:blank"]):
            with self.subTest(command=argv[0]):
                r = self.run_lab(*argv)
                text = r.stdout + r.stderr
                m = re.search(r"MemAvailable\D{0,40}?(\d+)\s*MiB", text)
                if m is None:
                    self.fail(text)
                self.assertLess(abs(int(m.group(1)) - meminfo_mib()), meminfo_mib() * 0.25, text)
                self.assertGreaterEqual(len(re.findall(r"\d+\s*MiB", text)), 2, f"no typical lab costs: {text}")


class ListTest(DeskTest):
    def line_of(self, out, lab_id):
        lines = [x for x in out.splitlines() if re.search(rf"(?<![\w-]){re.escape(lab_id)}(?![\w-])", x)]
        self.assertEqual(len(lines), 1, f"lab {lab_id} in:\n{out}")
        return lines[0]

    def test_list_shows_every_lab_from_every_session(self):
        one, two = self.session(), self.session()
        term = self.start(session=one)
        page = self.browse("--window", "about:blank", session=two)
        headless = self.browse(session=one)
        out = self.ok("list", session=self.session()).stdout
        for lab_id, kind, owner, placed in ((term, "terminal", one, True), (page, "browser", two, True),
                                           (headless, "browser", one, False)):  # fmt: skip
            with self.subTest(lab=lab_id, kind=kind, placed=placed):
                line = self.line_of(out, lab_id)
                for word in (kind, str(owner.pid), "alive"):
                    self.assertIn(word, line)
                if placed:
                    self.assertIn(SPARE, line)
                    self.assertIn(f"claude-lab-{lab_id}", line)
                else:
                    self.assertNotIn("claude-lab-", line)


class TeardownTest(DeskTest):
    def test_stop_ends_the_lab_and_leaves_the_workspaces_as_it_found_them(self):
        openers = {"terminal": lambda: self.start(), "windowed browser": lambda: self.browse("--window", "about:blank"),
                   "headless browser": lambda: self.browse()}  # fmt: skip
        for kind, opener in openers.items():
            with self.subTest(kind=kind):
                lab_id = opener()
                pid = self.launch()["pid"]
                self.ok("stop", "--lab", lab_id)
                wait_for(lambda pid=pid: started(pid) is None, timeout=5, what="the lab's app to exit")
                self.assertIsNone(self.workspace(lab_id))
                self.assertEqual(self.shape(), self.desk.start_shape)
                self.assertFalse(self.state_dir(lab_id).exists(), "the lab's state outlived it")
                self.assertFalse((self.cache / "niri-screen-lab" / lab_id).exists(), "the profile outlived the lab")
                if kind != "headless browser":
                    self.assertIn({"reference": {"Name": f"claude-lab-{lab_id}"}}, self.actions("UnsetWorkspaceName"))


class SweepTest(DeskTest):
    def dead_lab(self, kind):
        """A lab whose owner still runs but whose app is gone: a recording terminal lab, or a headless browser.

        Returns its id and its cast sessions."""
        owner = self.session()
        if kind == "terminal":
            lab_id = self.start(session=owner)
            self.ok("rec-start", "--lab", lab_id, session=owner)
            self.assertTrue(self.desk.sessions, "recording a terminal lab started no cast session")
        else:
            lab_id = self.browse(session=owner)
        casts, pid = set(self.desk.sessions), self.launch()["pid"]
        os.kill(pid, signal.SIGTERM)
        wait_for(lambda: started(pid) is None, what="the lab's app to exit")
        return lab_id, casts

    def test_any_sessions_list_start_or_browse_sweeps_a_dead_lab(self):
        for kind in ("terminal", "headless browser"):
            for argv in (["list"], ["start", "--", "cat"], ["browse", "about:blank"]):
                with self.subTest(kind=kind, command=argv[0]):
                    lab_id, casts = self.dead_lab(kind)
                    r = self.ok(*argv, session=self.session())
                    self.assertLessEqual(casts, set(self.desk.stopped), "a dead lab's cast session was left running")
                    self.assertIsNone(self.workspace(lab_id), "a dead lab's workspace kept its name")
                    self.assertFalse(self.state_dir(lab_id).exists(), "a dead lab's state was kept")
                    profile = self.cache / "niri-screen-lab" / lab_id
                    self.assertFalse(profile.exists(), "a dead lab's profile was kept")
                    if argv[0] == "list":
                        self.assertNotIn(lab_id, r.stdout)

    def test_a_dead_lab_is_swept_even_when_niri_cannot_be_reached(self):
        lab_id, _ = self.dead_lab("terminal")
        r = self.run_lab("list", unset=("NIRI_SOCKET",))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(lab_id, r.stdout)
        self.assertFalse(self.state_dir(lab_id).exists(), "a dead lab's state was kept")

    def test_without_a_runtime_dir_no_command_touches_the_working_directory(self):
        # lab.py runs in self.tmp; a relative screen-lab/ there is the user's, not the lab's
        notes = self.tmp / "screen-lab" / "notes"
        notes.mkdir(parents=True)
        (notes / "state.json").write_text('{"id": "notes", "kind": "terminal", "pid": 999999, "owner": 999999}')
        before = sorted(p.name for p in (self.tmp / "screen-lab").rglob("*"))
        for argv in (["list"], ["stop", "--lab", "notes"], ["start", "--", "cat"], ["browse", "about:blank"]):
            with self.subTest(command=argv[0]):
                r = self.run_lab(*argv, unset=("XDG_RUNTIME_DIR",))
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("XDG_RUNTIME_DIR", r.stderr)
                self.assertEqual(sorted(p.name for p in (self.tmp / "screen-lab").rglob("*")), before)


if __name__ == "__main__":
    unittest.main()
