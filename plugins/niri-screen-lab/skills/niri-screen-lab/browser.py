#!/usr/bin/env python3
"""The browser lab's side of niri-screen-lab: Chromium's flags, a stdlib-only DevTools (CDP) client, key events,
and the keeper that holds file choosers back.

`python3 browser.py keep STATE_DIR PORT` runs the keeper. lab.py starts it next to Chromium. See reference.md.
"""

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request
from pathlib import Path

# Values the lab needs that differ from Chromium's defaults. The profile is fresh for every lab.
CHROMIUM_FLAGS = [
    "--remote-debugging-port=0",  # a free port, written to DevToolsActivePort in the profile
    "--no-first-run",
    "--no-default-browser-check",
    "--password-store=basic",  # never the user's keyring
    "--deny-permission-prompts",
    "--disable-notifications",
    # showOpenFilePicker and friends would open a portal dialog, which the keeper can't hold back;
    # pages then fall back to <input type=file>, which it can.
    "--disable-blink-features=FileSystemAccessLocal",
    "--test-type",  # no "unsupported command-line flag" bar over the page for the line above
    "--new-window",
]
# Magenta squares in the viewport's top-left and bottom-right corners: start finds the viewport with them.
# No "#" in it: in a data: URL that starts the fragment and cuts the page off.
MARKER = 24
MARKER_PAGE = (
    "data:text/html,<body style='margin:0;background:white'>"
    f"<div style='position:fixed;left:0;top:0;width:{MARKER}px;height:{MARKER}px;background:rgb(255,0,255)'></div>"
    f"<div style='position:fixed;right:0;bottom:0;width:{MARKER}px;height:{MARKER}px;background:rgb(255,0,255)'></div>"
)


class CDPError(Exception):
    pass


def prepare_profile(profile, downloads):
    """A fresh profile whose downloads go to the lab's folder, never the user's, and never ask where."""
    (profile / "Default").mkdir(parents=True)
    downloads.mkdir(parents=True, exist_ok=True)
    prefs = {"download": {"default_directory": str(downloads), "prompt_for_download": False}}
    (profile / "Default" / "Preferences").write_text(json.dumps(prefs))


def devtools_port(profile, timeout=10.0):
    path = Path(profile) / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return int(path.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            time.sleep(0.1)
    raise CDPError("Chromium wrote no DevToolsActivePort")


def endpoints(port, kind):
    """The WebSocket URL of the browser (kind "browser") or of the first page tab (kind "page")."""
    base = f"http://127.0.0.1:{port}/json"
    if kind == "browser":
        return json.load(urllib.request.urlopen(f"{base}/version", timeout=5))["webSocketDebuggerUrl"]
    pages = [t for t in json.load(urllib.request.urlopen(base, timeout=5)) if t["type"] == "page"]
    if not pages:
        raise CDPError("the lab browser has no page open")
    return pages[0]["webSocketDebuggerUrl"]


def frame(payload, mask=None):
    """One masked client-to-server WebSocket text frame (RFC 6455, section 5.2)."""
    mask = mask or os.urandom(4)
    n = len(payload)
    if n < 126:
        head = bytes([0x81, 0x80 | n])
    elif n < 1 << 16:
        head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class CDP:
    """A blocking DevTools connection over one WebSocket. Unmasked server frames only, as Chromium sends."""

    def __init__(self, url, timeout=30.0):
        host, path = url.removeprefix("ws://").split("/", 1)
        name, port = host.rsplit(":", 1)
        self.sock = socket.create_connection((name, int(port)), timeout=timeout)
        try:
            self.buf = self._handshake(host, path)
        except BaseException:
            self.sock.close()
            raise
        self.next_id = 0
        self.events = []

    def _handshake(self, host, path):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("DevTools closed the connection during the handshake")
            head += chunk
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status + b" ":
            raise CDPError(f"DevTools refused the WebSocket: {status.decode(errors='replace')}")
        return head.split(b"\r\n\r\n", 1)[1]

    def _take(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise CDPError("DevTools closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """The next message, joining continuation frames. Raises CDPError when the browser goes away."""
        data = b""
        while True:
            b0, b1 = self._take(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._take(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._take(8))[0]
            payload = self._take(n)
            if b0 & 0x0F == 0x8:
                raise CDPError("DevTools closed the connection")
            if b0 & 0x0F in (0x9, 0xA):  # ping, pong: Chromium doesn't ping clients
                continue
            data += payload
            if b0 & 0x80:
                return json.loads(data)

    def post(self, method, session=None, **params):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params}
        if session:
            msg["sessionId"] = session
        self.sock.sendall(frame(json.dumps(msg).encode()))
        return self.next_id

    def call(self, method, session=None, **params):
        """Send a command and return its result; events that arrive meanwhile are kept in self.events."""
        want = self.post(method, session, **params)
        while True:
            msg = self.recv()
            if msg.get("id") == want:
                if "error" in msg:
                    raise CDPError(f"{method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def close(self):
        self.sock.close()


def evaluate(cdp, expression):
    """Run JavaScript in the page and return its JSON value; a thrown error becomes CDPError."""
    r = cdp.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r:
        d = r["exceptionDetails"]
        raise CDPError(f"the page threw: {d.get('exception', {}).get('description') or d.get('text')}")
    return r.get("result", {}).get("value")


def navigate(cdp, url, timeout=30.0):
    r = cdp.call("Page.navigate", url=url)
    if r.get("errorText"):
        raise CDPError(f"could not open {url}: {r['errorText']}")
    deadline = time.monotonic() + timeout
    while evaluate(cdp, "document.readyState") != "complete":
        if time.monotonic() > deadline:
            raise CDPError(f"{url} did not finish loading in {timeout:.0f}s")
        time.sleep(0.1)


# ---------- keys ----------

# name -> (DOM key, DOM code, Windows virtual key code, text it types)
KEYS = {
    "enter": ("Enter", "Enter", 13, "\r"),
    "esc": ("Escape", "Escape", 27, ""),
    "tab": ("Tab", "Tab", 9, ""),
    "backspace": ("Backspace", "Backspace", 8, ""),
    "space": (" ", "Space", 32, " "),
    "up": ("ArrowUp", "ArrowUp", 38, ""),
    "down": ("ArrowDown", "ArrowDown", 40, ""),
    "left": ("ArrowLeft", "ArrowLeft", 37, ""),
    "right": ("ArrowRight", "ArrowRight", 39, ""),
    "home": ("Home", "Home", 36, ""),
    "end": ("End", "End", 35, ""),
    "pgup": ("PageUp", "PageUp", 33, ""),
    "pgdn": ("PageDown", "PageDown", 34, ""),
    "delete": ("Delete", "Delete", 46, ""),
}
# CDP's Input.dispatchKeyEvent modifier bits.
MODIFIERS = {"alt": 1, "ctrl": 2, "meta": 4, "shift": 8}
# Raw bytes that `keys` turns into key presses instead of typed text.
CONTROL = {"\r": "enter", "\n": "enter", "\t": "tab", "\x1b": "esc", "\x7f": "backspace", "\b": "backspace"}


def key_event(name):
    """A key name like `enter`, `ctrl-a` or `ctrl-shift-p` -> (DOM key, code, key code, text, modifier bits)."""
    *mods, base = name.split("-") if name != "-" else ["-"]
    bits = 0
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier {m!r} in {name!r}; known: {', '.join(MODIFIERS)}")
        bits |= MODIFIERS[m]
    if base in KEYS:
        key, code, vk, text = KEYS[base]
    elif len(base) == 1:
        char = base.upper() if bits & MODIFIERS["shift"] else base
        key, text = char, char
        code = f"Key{base.upper()}" if base.isalpha() else (f"Digit{base}" if base.isdigit() else "")
        vk = ord(base.upper()) if base.isalnum() else 0
    else:
        raise ValueError(f"unknown key {base!r}; known: {', '.join(KEYS)}, or one character")
    if bits & (MODIFIERS["ctrl"] | MODIFIERS["alt"] | MODIFIERS["meta"]):
        text = ""  # a shortcut, not typing
    return key, code, vk, text, bits


def press(cdp, name):
    key, code, vk, text, bits = key_event(name)
    common = {"key": key, "code": code, "windowsVirtualKeyCode": vk, "modifiers": bits}
    cdp.call("Input.dispatchKeyEvent", type="keyDown" if text else "rawKeyDown", text=text, **common)
    cdp.call("Input.dispatchKeyEvent", type="keyUp", **common)


def type_text(cdp, text):
    """Type text: printable runs are inserted, control characters (\\r \\t \\e ...) pressed as keys."""
    run = ""
    for ch in text:
        if ch in CONTROL:
            if run:
                cdp.call("Input.insertText", text=run)
                run = ""
            press(cdp, CONTROL[ch])
        else:
            run += ch
    if run:
        cdp.call("Input.insertText", text=run)


def mouse(cdp, kind, x, y, button="none", clicks=0, **extra):
    cdp.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button=button, clickCount=clicks, **extra)


# ---------- the keeper ----------


def keep(state, port):
    """Hold a browser-wide session that intercepts every page's file chooser and logs it, until Chromium exits.

    Interception lasts only as long as the session that asked for it, so it lives here, not in a lab.py command.
    """
    log = open(Path(state) / "filechooser.log", "a", buffering=1)  # noqa: SIM115 -- open for the keeper's life
    cdp = CDP(endpoints(port, "browser"), timeout=None)
    cdp.post("Target.setAutoAttach", autoAttach=True, waitForDebuggerOnStart=False, flatten=True)
    while True:
        try:
            msg = cdp.recv()
        except (CDPError, OSError):
            return
        handle(cdp, msg, log)


def handle(cdp, msg, log):
    method = msg.get("method")
    if method == "Target.attachedToTarget" and msg["params"]["targetInfo"]["type"] == "page":
        session = msg["params"]["sessionId"]
        cdp.post("Page.enable", session)
        cdp.post("Page.setInterceptFileChooserDialog", session, enabled=True)
    elif method == "Page.fileChooserOpened":
        p = msg["params"]
        log.write(json.dumps({"time": time.time(), "mode": p.get("mode"), "backendNodeId": p.get("backendNodeId")}))
        log.write("\n")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "keep":
        keep(sys.argv[2], int(sys.argv[3]))
    else:
        sys.exit("usage: browser.py keep STATE_DIR PORT")
