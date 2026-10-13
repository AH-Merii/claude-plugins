"""The fake programs labtest.py puts on PATH. Each reports to the Desk at $NIRI_SOCKET (see fakedesk.py).

- niri: `niri msg [--json] outputs|workspaces|windows|focused-output|focused-window|casts|version|event-stream`.
  It takes no actions: they carry workspace ids, which only the socket accepts.
- gdbus: `gdbus call --session --dest org.gnome.Mutter.ScreenCast --object-path P --method I.M [ARGS]` for
  CreateSession, RecordWindow ({'window-id': <uint64 W>}), Start and Stop, printing GVariant text as gdbus does.
- gst-launch-1.0: reads `path=NODE` and an optional `num-buffers=N`, and writes one PNG per new frame to
  `multifilesink location=...%05d...`, `filesink location=...` or `fdsink`, until N frames or SIGINT/SIGTERM.
- ghostty: runs its `-e` command in a pty of 80x24 cells (800x480 px), opens its window, and reports output.
- chromium: serves DevTools on a free port, written to DevToolsActivePort, and opens a window unless
  `--headless=new`. Its page P1 is in browser window 1. A browser session that sets auto-attach is told of
  every page; evaluating `window.open(...)` adds a page in a new window and tells those sessions of it.
- ffmpeg: writes a stand-in GIF to its last argument.
- grim, wf-recorder, busctl: the lab must never run them; they record that they ran and fail.
"""

import base64
import contextlib
import fcntl
import hashlib
import json
import os
import pty
import re
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import zlib
from pathlib import Path
from typing import NoReturn

import fakedesk

SOCK = os.environ.get("NIRI_SOCKET", "")


def desk(op, **fields):
    reply = fakedesk.request(SOCK, {"Fake": {"op": op, **fields}})
    return reply.get("Ok")


def fail(msg) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(1)


# ---------- niri ----------

QUERIES = {"outputs": "Outputs", "workspaces": "Workspaces", "windows": "Windows", "focused-output": "FocusedOutput",
           "focused-window": "FocusedWindow", "casts": "Casts"}  # fmt: skip


def niri(argv):
    if argv[:1] == ["validate"]:
        return
    if argv[:1] != ["msg"]:
        fail(f"fake niri: unsupported {argv}")
    rest = [a for a in argv[1:] if a not in ("--json", "-j")]
    sub = rest[0] if rest else ""
    if sub == "version":
        print(json.dumps({"cli": "26.04 (fake)", "compositor": "26.04 (fake)"}))
    elif sub == "event-stream":
        s = socket.socket(socket.AF_UNIX)
        s.connect(SOCK)
        s.sendall(b'"EventStream"\n')
        f = s.makefile()
        f.readline()
        for line in f:
            print(line, end="", flush=True)
    elif sub in QUERIES:
        reply = fakedesk.request(SOCK, QUERIES[sub])
        if "Err" in reply:
            fail(reply["Err"])
        print(json.dumps(next(iter(reply["Ok"].values()))))
    else:
        fail(f"fake niri: `niri msg {sub}` is unsupported; send actions over $NIRI_SOCKET")


# ---------- gdbus ----------

BUS = "org.gnome.Mutter.ScreenCast"
OPTS = {"--dest": "dest", "-d": "dest", "--object-path": "path", "-o": "path", "--method": "method", "-m": "method",
        "--timeout": "timeout", "-t": "timeout"}  # fmt: skip


def gdbus(argv):
    if argv[:1] != ["call"]:
        fail(f"fake gdbus: only `gdbus call` is supported, not {argv[:1]}")
    o, params, it = {}, [], iter(argv[1:])
    for a in it:
        key, eq, value = a.partition("=")
        if key in OPTS:
            o[OPTS[key]] = value if eq else next(it, "")
        elif a not in ("--session", "-e"):
            params.append(a)
    if o.get("dest") != BUS:
        fail(f"Error: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown: {o.get('dest')}")
    iface, _, method = o.get("method", "").rpartition(".")
    path = o.get("path", "")
    if method == "CreateSession" and iface == BUS and path == "/org/gnome/Mutter/ScreenCast":
        out = desk("create")
    elif method == "RecordWindow" and iface == BUS + ".Session":
        m = re.search(r"window-id['\"]?\s*:\s*<\s*(?:uint64\s+)?(\d+)\s*>", " ".join(params))
        if not m:
            fail(f"Error: GDBus.Error:org.freedesktop.DBus.Error.InvalidArgs: no window-id in {params}")
        out = desk("record", session=path, window=int(m.group(1)))
    elif method in ("Start", "Stop") and iface == BUS + ".Session":
        out = desk(method.lower(), session=path)
    else:
        fail(f"Error: GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: {iface}.{method} on {path}")
    if isinstance(out, dict):
        fail(f"Error: {out['error']}")
    print(out if out == "()" else f"(objectpath '{out}',)")


# ---------- gst-launch-1.0 ----------


def gst(argv):
    desk("ran", tool="gst-launch-1.0", argv=argv)
    words = " ".join(argv).replace("!", " ! ").split()
    node = next((w.split("=", 1)[1] for w in words if w.startswith("path=")), None)
    if node is None:
        fail("fake gst-launch-1.0: no pipewiresrc path=NODE")
    count = int(next((w.split("=", 1)[1] for w in words if w.startswith("num-buffers=")), "0"))
    location = next((w.split("=", 1)[1].strip("'\"") for w in words if w.startswith("location=")), None)
    sink = next((w for w in words if w in ("multifilesink", "filesink", "fdsink")), None)
    stop = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.append(1))
    i = 0
    while not stop and (not count or i < count):
        r = desk("frame", node=int(node), consumer=os.getpid())
        if "error" in r:
            fail(f"ERROR: from element /GstPipeline:pipeline0/GstPipeWireSrc:pipewiresrc0: {r['error']}")
        if r["seq"] is None:  # no new frame yet
            time.sleep(0.02)
            continue
        data = fakedesk.frame_png(r["seq"], fakedesk.WINDOW, r["markers"])
        if sink == "fdsink":
            sys.stdout.buffer.write(data)
            sys.stdout.flush()
        elif sink == "filesink" and location:
            with open(location, "ab") as f:
                f.write(data)
        elif location:
            name = location % i if "%" in location else location
            tmp = name + ".part"
            Path(tmp).write_bytes(data)
            os.replace(tmp, name)
        i += 1
        time.sleep(0.05)


# ---------- ghostty ----------


def ghostty(argv):
    app_id = next(a.split("=", 1)[1] for a in argv if a.startswith("--class="))
    cwd = next((a.split("=", 1)[1] for a in argv if a.startswith("--working-directory=")), None)
    cmd = argv[argv.index("-e") + 1 :]
    desk("launch", app="ghostty", pid=os.getpid(), argv=argv, env=dict(os.environ))
    relay = [i for i, c in enumerate(cmd) if c.endswith("relay.py")]
    state_dir = cmd[relay[0] + 1] if relay else None
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 800, 480))
    child = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, start_new_session=True)
    os.close(slave)

    def end(*_):
        if child.pid > 1:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
        os._exit(0)

    signal.signal(signal.SIGTERM, end)
    time.sleep(0.1)  # the time a real window takes to map
    desk("open", pid=os.getpid(), app_id=app_id, state_dir=state_dir)
    while True:
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        desk("draw", pid=os.getpid(), text=data.decode(errors="replace"))
    end()


# ---------- chromium ----------


class DevTools:
    """Just enough of Chromium's DevTools: /json/version, /json, and a WebSocket per target."""

    def __init__(self):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.url, self.title, self.shots = "about:blank", "", 0
        self.windows = {"P1": 1}  # page target id -> its browser window
        self.attached = []  # send functions of the browser sessions that set auto-attach
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            conn, _ = self.listener.accept()
            threading.Thread(target=self.client, args=(conn,), daemon=True).start()

    def client(self, conn):
        with conn:
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                head += chunk
            lines = head.decode().split("\r\n")
            path = lines[0].split()[1]
            headers = {k.strip().lower(): v.strip() for k, _, v in (h.partition(":") for h in lines[1:] if h)}
            if headers.get("upgrade", "").lower() == "websocket":
                key = headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1(key.encode()).digest()).decode()
                conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                             f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode())  # fmt: skip
                self.socket_loop(conn, path)
                return
            ws = f"ws://127.0.0.1:{self.port}/devtools"
            body = {"/json/version": {"Browser": "Chrome/fake", "webSocketDebuggerUrl": f"{ws}/browser/fake"}}.get(
                path, [{"id": "P1", "type": "page", "url": self.url, "webSocketDebuggerUrl": f"{ws}/page/P1"}]
            )
            data = json.dumps(body).encode()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(data)
                         + data)  # fmt: skip

    def socket_loop(self, conn, path):
        f, lock = conn.makefile("rb"), threading.Lock()

        def send(obj):
            data = json.dumps(obj).encode()
            n = len(data)
            size = bytes([n]) if n < 126 else (bytes([126]) + struct.pack(">H", n) if n < 1 << 16
                                                 else bytes([127]) + struct.pack(">Q", n))  # fmt: skip
            with lock:
                conn.sendall(b"\x81" + size + data)

        while True:
            head = f.read(2)
            if len(head) < 2:
                return
            n = head[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", f.read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", f.read(8))[0]
            mask = f.read(4) if head[1] & 0x80 else b"\0\0\0\0"
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(f.read(n)))
            if head[0] & 0x0F == 0x8:
                return
            msg = json.loads(payload)
            reply = {"id": msg["id"], "result": self.handle(msg["method"], msg.get("params", {}))}
            if "sessionId" in msg:
                reply["sessionId"] = msg["sessionId"]
            send(reply)
            if msg["method"] == "Target.setAutoAttach" and "/browser/" in path:
                self.attached.append(send)
                for target in list(self.windows):
                    send(self.attached_to(target))

    @staticmethod
    def attached_to(target):
        info = {"targetId": target, "type": "page", "url": "about:blank"}
        return {"method": "Target.attachedToTarget", "params": {"sessionId": f"S-{target}", "targetInfo": info}}

    def handle(self, method, params):
        desk("cdp", pid=os.getpid(), method=method, params={k: v for k, v in params.items() if k != "data"})
        if method == "Page.captureScreenshot":
            self.shots += 1
            return {"data": base64.b64encode(fakedesk.frame_png(self.shots, fakedesk.VIEWPORT)).decode()}
        if method == "Page.navigate":
            self.url = params.get("url", "")
            return {"frameId": "F1"}
        if method == "Browser.getWindowForTarget":
            return {"windowId": self.windows[params["targetId"]], "bounds": {}}
        if method == "Runtime.evaluate":
            e = params.get("expression", "")
            if "window.open(" in e:
                target = f"P{len(self.windows) + 1}"
                self.windows[target] = len(self.windows) + 1
                for send in self.attached:
                    send(self.attached_to(target))
                value = None
            elif "readyState" in e:
                value = "complete"
            elif "innerWidth" in e:
                value = list(fakedesk.VIEWPORT)
            elif "location.href" in e:
                value = {"url": self.url, "title": self.title}
            elif e.strip() == "document.title":
                value = self.title
            else:
                value = None
            return {"result": {"type": "object", "value": value}}
        return {}


def chromium(argv):
    app_id = next((a.split("=", 1)[1] for a in argv if a.startswith("--class=")), "chromium")
    profile = next(a.split("=", 1)[1] for a in argv if a.startswith("--user-data-dir="))
    desk("launch", app="chromium", pid=os.getpid(), argv=argv, env=dict(os.environ))
    tools = DevTools()
    Path(profile).mkdir(parents=True, exist_ok=True)
    (Path(profile) / "DevToolsActivePort").write_text(f"{tools.port}\n/devtools/browser/fake\n")
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    if "--headless=new" not in argv:
        time.sleep(0.1)
        desk("open", pid=os.getpid(), app_id=app_id, state_dir=None)
    while True:
        signal.pause()


# ---------- the rest ----------


def ffmpeg(argv):
    desk("ran", tool="ffmpeg", argv=argv)
    pattern, n = argv[argv.index("-i") + 1], int(argv[argv.index("-start_number") + 1])
    while os.path.exists(pattern % n):  # which cast frames the GIF is made of; a browser's aren't stamped
        with contextlib.suppress(ValueError, IndexError, struct.error, zlib.error):
            desk("gif-frame", seq=fakedesk.seq_of(Path(pattern % n).read_bytes()))
        n += 1
    Path(argv[-1]).write_bytes(b"GIF89a" + b"\0" * 64)


def forbidden(tool):
    def run(argv):
        desk("ran", tool=tool, argv=argv)
        fail(f"fake {tool}: the lab must not run {tool}")

    return run


TOOLS = {"niri": niri, "gdbus": gdbus, "gst-launch-1.0": gst, "ghostty": ghostty, "chromium": chromium,
         "ffmpeg": ffmpeg, **{t: forbidden(t) for t in ("grim", "wf-recorder", "busctl")}}  # fmt: skip
FORBIDDEN_TOOLS = {"grim", "wf-recorder", "busctl"}

GI = """
import re


class Application:
    @staticmethod
    def id_is_valid(app_id):
        return bool(re.fullmatch(r"[A-Za-z_][\\w-]*(\\.[A-Za-z_][\\w-]*)+", app_id))


class Gio:
    Application = Application
"""


def install(bin_dir, py_dir):
    """Write a shim for every fake into `bin_dir`, and a stand-in for PyGObject's Gio into `py_dir`."""
    here = os.path.dirname(os.path.abspath(__file__))
    for tool in TOOLS:
        p = Path(bin_dir) / tool
        p.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {here!r})\nimport fakebin\n"
                     f"fakebin.TOOLS[{tool!r}](sys.argv[1:])\n")  # fmt: skip
        p.chmod(0o755)
    gi = Path(py_dir) / "gi"
    gi.mkdir(parents=True)
    (gi / "__init__.py").write_text("")
    (gi / "repository.py").write_text(GI)
