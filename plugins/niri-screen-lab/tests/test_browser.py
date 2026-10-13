"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

The browser lab's rules that need no desktop: a page gets no input while the lab window has
focus (only a focused client can set the clipboard), browser-only commands refuse a terminal lab,
keys and pixels map the way hover, click and `keys` rely on, and the DevTools client reads what
Chromium sends. niri is the outside boundary: find_window is replaced where a rule depends on it.
"""

import json
import shutil
import socket
import struct
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from test_owner import commands, lab, lab_process, sleeper

browser = lab.browser  # test_owner puts the skill's folder on sys.path

# Commands that act on the page, and so must refuse while the lab window has focus.
PAGE_INPUT = {
    "keys": ["keys", "hi"],
    "key": ["key", "enter"],
    "hover": ["hover", "10", "10"],
    "click": ["click", "10", "10"],
    "scroll": ["scroll", "down", "10", "10"],
    "open": ["open", "about:blank"],
    "js": ["js", "1"],
}
NOT_PAGE_INPUT = {
    "preflight", "doctor", "start", "browse", "info", "cell", "shot", "gif", "rec-start", "rec-stop", "stop",
}  # fmt: skip


class LabStateTest(unittest.TestCase):
    """Runs commands in-process against a state dir of its own, with a renamed sleep as the lab's process."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name) / "screen-lab"
        state.mkdir(mode=0o700)
        for name, value in (("STATE", state), ("STATE_FILE", state / "state.json"), ("FEED", state / "feed")):
            patcher = mock.patch.object(lab, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = Path(tmp.name)

    def make_lab(self, kind, focused):
        fake = self.tmp / {"browser": "chromium", "terminal": "ghostty"}[kind]
        shutil.copy(shutil.which("sleep") or "/usr/bin/sleep", fake)
        p = sleeper(str(fake))
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        # Port 9 (discard) has no DevTools: a command that gets past its checks fails to connect.
        lab.save_state({"kind": kind, **lab_process(p.pid), "output": "eDP-1", "port": 9, "owner": None})
        window = {"id": 1, "is_focused": focused, "layout": {"window_size": [100, 100]}}
        patcher = mock.patch.object(lab, "find_window", return_value=window)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, argv):
        a = lab.parser().parse_args(argv)
        return a.fn(a)


class FocusTest(LabStateTest):
    def test_every_command_is_classified(self):
        self.assertIn("click", PAGE_INPUT)
        self.assertEqual(commands(), set(PAGE_INPUT) | NOT_PAGE_INPUT)

    def test_page_input_is_refused_while_the_lab_window_has_focus(self):
        self.make_lab("browser", focused=True)
        for name, argv in PAGE_INPUT.items():
            with self.subTest(command=name), self.assertRaisesRegex(lab.Refuse, "has focus"):
                self.run_cmd(argv)

    def test_page_input_goes_ahead_while_the_lab_window_is_unfocused(self):
        self.make_lab("browser", focused=False)
        for name, argv in PAGE_INPUT.items():
            # Past the focus check, the command tries DevTools on a port with nothing behind it.
            with self.subTest(command=name), self.assertRaises(OSError):
                self.run_cmd(argv)


class KindTest(LabStateTest):
    def test_browser_only_commands_refuse_a_terminal_lab(self):
        self.make_lab("terminal", focused=False)
        for argv in (["open", "about:blank"], ["js", "1"]):
            with self.subTest(command=argv[0]), self.assertRaisesRegex(lab.Refuse, "needs a browser lab"):
                self.run_cmd(argv)


class KeysTest(unittest.TestCase):
    def test_key_names_map_to_dom_keys_and_shortcuts_type_nothing(self):
        cases = {
            # name: (DOM key, code, key code, text, modifier bits)
            "enter": ("Enter", "Enter", 13, "\r", 0),
            "a": ("a", "KeyA", 65, "a", 0),
            "shift-a": ("A", "KeyA", 65, "A", 8),
            "ctrl-a": ("a", "KeyA", 65, "", 2),
            "ctrl-shift-p": ("P", "KeyP", 80, "", 10),
            "alt-1": ("1", "Digit1", 49, "", 1),
            "esc": ("Escape", "Escape", 27, "", 0),
        }
        for name, want in cases.items():
            with self.subTest(key=name):
                self.assertEqual(browser.key_event(name), want)

    def test_unknown_keys_and_modifiers_are_refused(self):
        for name in ("bogus", "hyper-a", "ctrl-bogus"):
            with self.subTest(key=name), self.assertRaises(ValueError):
                browser.key_event(name)

    def test_typing_inserts_text_and_presses_control_characters(self):
        sent = []

        class Recorder:
            def call(self, method, session=None, **params):
                sent.append((method, params.get("text") if method == "Input.insertText" else params["key"]))

        browser.type_text(Recorder(), "ab\rc\x1b")
        self.assertEqual(
            sent,
            [
                ("Input.insertText", "ab"),
                ("Input.dispatchKeyEvent", "Enter"),
                ("Input.dispatchKeyEvent", "Enter"),
                ("Input.insertText", "c"),
                ("Input.dispatchKeyEvent", "Escape"),
                ("Input.dispatchKeyEvent", "Escape"),
            ],
        )


# A 200x100 px viewport at (10, 20) in the output, showing a page 100x50 CSS pixels wide: 2 px per CSS pixel.
VIEWPORT = {"x": 10, "y": 20, "width": 200, "height": 100, "css_width": 100, "css_height": 50}


class PixelTest(unittest.TestCase):
    def test_screenshot_pixels_map_to_page_pixels(self):
        self.assertEqual(lab.css_point(VIEWPORT, 110, 70, crop=False), (50, 25))
        self.assertEqual(lab.css_point(VIEWPORT, 100, 50, crop=True), (50, 25))
        self.assertEqual(lab.css_point(VIEWPORT, 10, 20, crop=False), (0, 0))

    def test_pixels_outside_the_viewport_map_to_nothing(self):
        for x, y, crop in ((5, 70, False), (110, 15, False), (210, 70, False), (200, 10, True)):
            with self.subTest(x=x, y=y, crop=crop):
                self.assertIsNone(lab.css_point(VIEWPORT, x, y, crop))

    def test_only_the_two_marker_squares_count_as_the_viewport(self):
        # A 936x927 CSS viewport at scale 1: two 24x24 squares are 1152 magenta pixels.
        self.assertTrue(lab.plausible_viewport((0, 0, 936, 927, 1152, None), 936, 927))
        self.assertFalse(lab.plausible_viewport((0, 0, 936, 927, 5000, None), 936, 927), "magenta wallpaper")
        self.assertFalse(lab.plausible_viewport((0, 0, 936, 927, 1152, None), 936, 500), "scales disagree")


def server_frame(payload, final=True, opcode=0x1):
    n = len(payload)
    first = (0x80 if final else 0) | opcode
    if n < 126:
        return bytes([first, n]) + payload
    if n < 1 << 16:
        return bytes([first, 126]) + struct.pack(">H", n) + payload
    return bytes([first, 127]) + struct.pack(">Q", n) + payload


class FakeDevTools:
    """Accepts one connection, answers the handshake with `status`, then sends `frames` and holds on."""

    def __init__(self, status, frames=()):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.url = f"ws://127.0.0.1:{self.listener.getsockname()[1]}/devtools/page/X"
        self.status, self.frames = status, frames
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.listener.accept()
        with conn:
            head = b""
            while b"\r\n\r\n" not in head:
                head += conn.recv(4096)
            conn.sendall(f"HTTP/1.1 {self.status}\r\n\r\n".encode())
            conn.recv(4096)  # the command
            for f in self.frames:
                conn.sendall(f)
            conn.recv(4096)  # until the client closes

    def close(self):
        self.listener.close()


class CDPTest(unittest.TestCase):
    def connect(self, status, frames=()):
        server = FakeDevTools(status, frames)
        self.addCleanup(server.close)
        cdp = browser.CDP(server.url, timeout=5)
        self.addCleanup(cdp.close)
        return cdp

    def test_a_call_returns_its_own_reply_and_keeps_the_events_before_it(self):
        big = json.dumps({"method": "Page.big", "params": {"pad": "x" * 70000}}).encode()
        reply = json.dumps({"id": 1, "result": {"value": 42}}).encode()
        frames = [
            server_frame(big),  # a 64-bit length
            server_frame(b'{"method": "Page.split", ', final=False),
            server_frame(b'"params": {}}', opcode=0x0),
            server_frame(reply),
        ]
        cdp = self.connect("101 Switching Protocols", frames)
        self.assertEqual(cdp.call("Runtime.evaluate", expression="42"), {"value": 42})
        self.assertEqual([e["method"] for e in cdp.events], ["Page.big", "Page.split"])

    def test_an_error_reply_raises_with_its_message(self):
        reply = json.dumps({"id": 1, "error": {"code": -32000, "message": "Cannot navigate"}}).encode()
        cdp = self.connect("101 Switching Protocols", [server_frame(reply)])
        with self.assertRaisesRegex(browser.CDPError, "Cannot navigate"):
            cdp.call("Page.navigate", url="x")

    def test_a_refused_handshake_raises(self):
        server = FakeDevTools("403 Forbidden")
        self.addCleanup(server.close)
        with self.assertRaisesRegex(browser.CDPError, "403"):
            browser.CDP(server.url, timeout=5)

    def test_client_frames_are_masked_with_their_length(self):
        payload = b"x" * 300
        f = browser.frame(payload, mask=b"\x01\x02\x03\x04")
        self.assertEqual(f[:4], bytes([0x81, 0x80 | 126]) + struct.pack(">H", 300))
        self.assertEqual(f[4:8], b"\x01\x02\x03\x04")
        self.assertEqual(bytes(b ^ (1, 2, 3, 4)[i % 4] for i, b in enumerate(f[8:])), payload)


class MarkerPageTest(unittest.TestCase):
    def test_the_whole_marker_page_reaches_the_browser(self):
        # A "#" in a data: URL starts the fragment: the markers after it would never render.
        parts = urllib.parse.urlsplit(browser.MARKER_PAGE)
        self.assertEqual(parts.fragment, "")
        self.assertEqual(parts.path.count("position:fixed"), 2)


class ProfileTest(unittest.TestCase):
    def test_downloads_go_to_the_lab_folder_without_asking(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, downloads = Path(tmp) / "profile", Path(tmp) / "downloads"
            browser.prepare_profile(profile, downloads)
            prefs = json.loads((profile / "Default" / "Preferences").read_text())
            self.assertEqual(prefs["download"], {"default_directory": str(downloads), "prompt_for_download": False})
            self.assertTrue(downloads.is_dir())


if __name__ == "__main__":
    unittest.main()
