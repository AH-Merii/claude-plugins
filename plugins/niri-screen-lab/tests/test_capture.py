"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

Capture works on hidden workspaces without the clipboard or focus. A terminal lab is captured through
niri's org.gnome.Mutter.ScreenCast service (gdbus) and decoded with GStreamer: its first frame is stale
and dropped, a shot after input shows a frame drawn after it, and every cast session is stopped when the
lab stops. A browser lab, headless or windowed, is captured with Page.captureScreenshot.
"""

import time
import unittest
from pathlib import Path

import fakedesk
from labtest import DeskTest, png_size, wait_for

GRID = fakedesk.GRID


def cell_centre(col, row):
    return GRID["x"] + (col - 0.5) * GRID["cell_w"], GRID["y"] + (row - 0.5) * GRID["cell_h"]


class TerminalCaptureTest(DeskTest):
    def shot(self, lab_id, *flags):
        out = self.tmp / f"shot-{time.monotonic_ns()}.png"
        self.ok("shot", str(out), *flags, "--lab", lab_id)
        return out

    def frame(self, path):
        """What the fake desk knows of the frame a PNG shows: {"drawn", "first", "node"}."""
        seq = fakedesk.seq_of(Path(path).read_bytes())
        self.assertIn(seq, self.desk.frames, "the shot is no frame a cast delivered")
        return self.desk.frames[seq]

    def test_a_shot_is_the_whole_lab_window_from_its_own_cast(self):
        a, b = self.start(), self.start()
        self.ok("rec-start", "--lab", a)  # lab a's cast is listed first while b is shot
        for lab_id in (b, a):
            with self.subTest(lab=lab_id):
                out = self.shot(lab_id)
                self.assertEqual(png_size(out), fakedesk.WINDOW)
                self.assertEqual(self.desk.nodes[self.frame(out)["node"]], self.window(lab_id)["id"])
        self.ok("rec-stop", str(self.tmp / "a.gif"), "--lab", a)

    def test_a_shot_after_input_shows_a_frame_drawn_after_the_input(self):
        period = 1.0  # niri draws a hidden window about once a second (src/niri.rs:189-192)
        lab_id = self.start()
        pid = self.window(lab_id)["pid"]
        with self.desk.lock:
            self.desk.frame_period = period
        self.shot(lab_id)  # a cast may already run; the next shot must still be fresh
        wait_for(lambda: time.time() % period < 0.1, what="the hidden window to be drawn")
        self.ok("keys", "fresh\\r", "--lab", lab_id)

        def typed():
            return [t for t, p, text in self.desk.draws if p == pid and "fresh" in text]

        wait_for(typed, what="the terminal to print the input")
        self.assertGreater(self.frame(self.shot(lab_id))["drawn"], typed()[0])

    def test_a_shot_never_shows_a_casts_stale_first_frame(self):
        lab_id = self.start()
        for _ in range(2):
            self.assertFalse(self.frame(self.shot(lab_id))["first"], "the shot is a cast's first, stale frame")

    def test_crop_and_cell_find_the_grid_in_cast_frames(self):
        lab_id = self.start()
        self.assertEqual(png_size(self.shot(lab_id, "--crop")), (GRID["cols"] * GRID["cell_w"],
                                                                  GRID["rows"] * GRID["cell_h"]))  # fmt: skip
        x, y = cell_centre(5, 3)
        self.assertEqual(self.ok("cell", str(x), str(y), "--lab", lab_id).stdout.split(), ["5", "3"])
        x, y = x - GRID["x"], y - GRID["y"]
        self.assertEqual(self.ok("cell", str(x), str(y), "--crop", "--lab", lab_id).stdout.split(), ["5", "3"])
        x, y = cell_centre(80, 24)
        self.assertEqual(self.ok("cell", str(x), str(y), "--lab", lab_id).stdout.split(), ["80", "24"])
        r = self.run_lab("cell", "2", "2", "--lab", lab_id)
        self.assertEqual(r.returncode, 1, "a pixel in the window's padding mapped to a cell")

    def test_gifs_and_recordings_come_from_the_labs_cast(self):
        lab_id = self.start()
        gif = self.tmp / "a.gif"
        self.ok("gif", str(gif), "0.5", "--lab", lab_id)
        self.ok("rec-start", "--lab", lab_id)
        time.sleep(0.3)
        rec = self.tmp / "b.gif"
        self.ok("rec-stop", str(rec), "--lab", lab_id)
        self.assertEqual(self.desk.casts_json(), [], "a finished recording left its cast session running")
        self.assertTrue(self.desk.gif_frames, "no cast frame reached a GIF")
        stale = [seq for seq in self.desk.gif_frames if self.desk.frames[seq]["first"]]
        self.assertEqual(stale, [], "a cast's stale first frame reached a GIF")
        for out in (gif, rec):
            self.assertEqual(out.read_bytes()[:6], b"GIF89a", out)
        window = self.window(lab_id)["id"]
        nodes = {f["node"] for f in self.desk.frames.values()}
        self.assertTrue(nodes and all(self.desk.nodes[n] == window for n in nodes))

    def test_every_cast_session_is_stopped_when_the_lab_stops(self):
        lab_id = self.start()
        self.shot(lab_id)
        self.ok("rec-start", "--lab", lab_id)
        self.assertTrue(self.desk.created, "no cast session was created")
        self.ok("stop", "--lab", lab_id)
        self.assertEqual(set(self.desk.created), set(self.desk.stopped))
        self.assertEqual(self.desk.casts_json(), [])


MODES = {"headless": (), "windowed": ("--window",)}


class BrowserCaptureTest(DeskTest):
    def test_a_browser_shot_is_a_devtools_screenshot_in_either_mode(self):
        for mode, flags in MODES.items():
            with self.subTest(mode=mode):
                lab_id = self.browse(*flags, "about:blank")
                pid = self.launch()["pid"]
                for crop in ((), ("--crop",)):
                    before = self.cdp_calls(pid).count("Page.captureScreenshot")
                    out = self.tmp / f"{mode}{''.join(crop)}.png"
                    self.ok("shot", str(out), *crop, "--lab", lab_id)
                    self.assertEqual(png_size(out), fakedesk.VIEWPORT)
                    self.assertGreater(self.cdp_calls(pid).count("Page.captureScreenshot"), before)
        self.assertEqual(self.desk.created, [], "a browser lab was captured through a screencast")

    def test_cell_maps_screenshot_pixels_to_page_pixels(self):
        lab_id = self.browse()
        self.assertEqual(self.ok("cell", "100", "50", "--lab", lab_id).stdout.split(), ["100", "50"])
        self.assertEqual(self.run_lab("cell", "900", "50", "--lab", lab_id).returncode, 1)

    def test_a_browser_gif_polls_screenshots(self):
        lab_id = self.browse()
        pid = self.launch()["pid"]
        gif = self.tmp / "page.gif"
        self.ok("gif", str(gif), "1", "--lab", lab_id)
        self.assertEqual(gif.read_bytes()[:6], b"GIF89a")
        self.assertGreaterEqual(self.cdp_calls(pid).count("Page.captureScreenshot"), 5, "fewer than 5 shots a second")

    def test_rec_stop_ends_the_polling(self):
        lab_id = self.browse()
        pid = self.launch()["pid"]
        self.ok("rec-start", "--lab", lab_id)
        wait_for(lambda: self.cdp_calls(pid).count("Page.captureScreenshot") >= 3, what="the recording to poll")
        self.ok("rec-stop", str(self.tmp / "rec.gif"), "--lab", lab_id)
        self.assertEqual((self.tmp / "rec.gif").read_bytes()[:6], b"GIF89a")
        polled = len(self.cdp_calls(pid))
        time.sleep(0.5)
        self.assertEqual(len(self.cdp_calls(pid)), polled, "polling went on after rec-stop")


if __name__ == "__main__":
    unittest.main()
