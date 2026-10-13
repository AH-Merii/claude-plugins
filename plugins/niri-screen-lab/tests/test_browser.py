"""Run with: python3 -m unittest discover -s plugins/niri-screen-lab/tests

The browser lab's rules: a windowed lab's page gets no input while its window has focus (only a focused
client can set the clipboard), while a headless lab has no window to focus; browser-only commands refuse
a terminal lab; keys map the way `key` and `keys` rely on; and the DevTools client reads what Chromium
sends and never asks it to raise or activate a target.
"""

import io
import json
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

from labtest import DeskTest, wait_for
from test_owner import commands, lab

browser = lab.browser  # test_owner puts the skill's folder on sys.path

# Commands that act on the page, and so must refuse while a windowed lab's window has focus.
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
    "preflight", "doctor", "list", "start", "browse", "info", "cell", "shot", "gif", "rec-start", "rec-stop", "stop",
}  # fmt: skip


def page_input(calls):
    return [m for m in calls if m.startswith("Input.") or m in ("Page.navigate", "Runtime.evaluate")]


class FocusTest(DeskTest):
    def test_every_command_is_classified(self):
        self.assertIn("click", PAGE_INPUT)
        self.assertEqual(commands(), set(PAGE_INPUT) | NOT_PAGE_INPUT)

    def test_page_input_is_refused_while_a_windowed_labs_window_has_focus(self):
        lab_id = self.browse("--window", "about:blank")
        pid = self.launch()["pid"]
        with self.desk.lock:
            self.desk.set_focus(self.window(lab_id)["id"])
        sent = len(page_input(self.cdp_calls(pid)))
        for name, argv in PAGE_INPUT.items():
            with self.subTest(command=name):
                r = self.run_lab(*argv, "--lab", lab_id)
                self.assertEqual(r.returncode, 1)
                self.assertIn("has focus", r.stderr)
        self.assertEqual(len(page_input(self.cdp_calls(pid))), sent, "a page got input while its window had focus")

    def test_page_input_is_refused_while_any_window_of_a_windowed_lab_has_focus(self):
        lab_id = self.browse("--window", "about:blank")
        pid = self.launch()["pid"]
        with self.desk.lock:  # a popup the page opened: a second, focused window of the same browser
            self.desk.set_focus(self.desk.open_window(pid, lab.APP_ID, None))
        sent = len(page_input(self.cdp_calls(pid)))
        r = self.run_lab("click", "10", "10", "--lab", lab_id)
        self.assertEqual(r.returncode, 1)
        self.assertIn("has focus", r.stderr)
        self.assertEqual(len(page_input(self.cdp_calls(pid))), sent, "a page got input while a lab window had focus")

    def test_page_input_goes_ahead_in_an_unfocused_or_headless_lab(self):
        for mode, flags in {"windowed": ("--window",), "headless": ()}.items():
            lab_id = self.browse(*flags, "about:blank")
            pid = self.launch()["pid"]
            for name, argv in PAGE_INPUT.items():
                with self.subTest(mode=mode, command=name):
                    sent = len(page_input(self.cdp_calls(pid)))
                    self.ok(*argv, "--lab", lab_id)
                    self.assertGreater(len(page_input(self.cdp_calls(pid))), sent)


class KindTest(DeskTest):
    def test_browser_only_commands_refuse_a_terminal_lab(self):
        lab_id = self.start()
        for argv in (["open", "about:blank"], ["js", "1"]):
            with self.subTest(command=argv[0]):
                r = self.run_lab(*argv, "--lab", lab_id)
                self.assertEqual(r.returncode, 1)
                self.assertIn("needs a browser lab", r.stderr)


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


class Listener:
    """Accepts one WebSocket and records every byte the client sends after the handshake."""

    def __init__(self):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.url = f"ws://127.0.0.1:{self.listener.getsockname()[1]}/devtools/page/X"
        self.received = b""
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.listener.accept()
        with conn:
            head = b""
            while b"\r\n\r\n" not in head:
                head += conn.recv(4096)
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
            while chunk := conn.recv(4096):
                self.received += chunk

    def close(self):
        self.listener.close()


class DenyTest(unittest.TestCase):
    def test_the_client_refuses_to_raise_or_activate_a_target_and_sends_nothing(self):
        for method in ("Page.bringToFront", "Target.activateTarget"):
            for how in ("call", "post"):
                with self.subTest(method=method, how=how):
                    server = Listener()
                    self.addCleanup(server.close)
                    cdp = browser.CDP(server.url, timeout=5)
                    with self.assertRaisesRegex(browser.CDPError, method):
                        getattr(cdp, how)(method)
                    cdp.close()
                    server.thread.join(timeout=5)
                    self.assertEqual(server.received, b"", f"{method} reached Chromium")


class Recorder:
    """Stands in for the keeper's DevTools connection: notes what it sends, numbering requests as Chromium would."""

    def __init__(self):
        self.sent = []

    def post(self, method, session=None, **params):
        self.sent.append((method, params))
        return len(self.sent)


class PopupTest(unittest.TestCase):
    def keeper_after(self, windowed, pages):
        """A keeper told that each page in `pages` (target id -> its browser window) opened, in order."""
        cdp = Recorder()
        keeper = browser.Keeper(cdp, io.StringIO(), windowed)
        for i, (target, window) in enumerate(pages.items()):
            info = {"type": "page", "targetId": target}
            keeper.handle({"method": "Target.attachedToTarget", "params": {"sessionId": f"S{i}", "targetInfo": info}})
            ask = ("Browser.getWindowForTarget", {"targetId": target})
            asked = [n for n, sent in enumerate(cdp.sent, 1) if sent == ask]
            if asked:
                keeper.handle({"id": asked[-1], "result": {"windowId": window, "bounds": {}}})
        return [p["targetId"] for m, p in cdp.sent if m == "Target.closeTarget"]

    def test_a_windowed_lab_closes_pages_that_open_in_a_new_window(self):
        closed = self.keeper_after(True, {"MAIN": 1, "TAB": 1, "POPUP": 2, "POPUP2": 3})
        self.assertEqual(closed, ["POPUP", "POPUP2"])

    def test_a_headless_lab_keeps_every_page(self):
        self.assertEqual(self.keeper_after(False, {"MAIN": 1, "TAB": 1, "POPUP": 2}), [])


class LabPopupTest(DeskTest):
    """What `browse` sets up: a windowed lab closes a popup, which would show on the user's screen, and a
    headless lab, which has no screen to show it on, keeps it."""

    def popup_after_browse(self, *flags):
        """Browse in a lab with `flags`, open a popup from the page, and return its pid once the popup's file
        chooser is intercepted, which happens in both modes."""
        lab_id = self.browse(*flags, "about:blank")
        pid = self.launch()["pid"]

        def intercepted():
            return self.cdp_calls(pid).count("Page.setInterceptFileChooserDialog")

        wait_for(lambda: intercepted() == 1, what="the keeper to attach to the lab's page")
        self.ok("js", "--lab", lab_id, "void window.open('about:blank', '', 'popup')")
        wait_for(lambda: intercepted() == 2, what="the keeper to attach to the popup")
        return pid

    def closed(self, pid):
        return [p["targetId"] for _, p_, m, p in self.desk.cdp if p_ == pid and m == "Target.closeTarget"]

    def test_a_windowed_lab_closes_a_popup(self):
        pid = self.popup_after_browse("--window")
        wait_for(lambda: self.closed(pid), what="the popup to be closed")
        self.assertEqual(self.closed(pid), ["P2"])

    def test_a_headless_lab_keeps_a_popup(self):
        pid = self.popup_after_browse()
        time.sleep(1)  # a windowed keeper closes it within this time (see the test above)
        self.assertEqual(self.closed(pid), [])


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
