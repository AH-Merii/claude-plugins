"""A fake desktop for the lab's tests: niri's IPC socket, its ScreenCast sessions, and their frames.

The lab's outside boundaries are niri (its socket at $NIRI_SOCKET and the `niri msg` CLI), D-Bus (`gdbus`),
GStreamer (`gst-launch-1.0`), and Ghostty or Chromium. fakebin.py puts a fake of each on PATH; they all talk
to one Desk, served on a Unix socket that stands in for $NIRI_SOCKET.

The Desk answers niri's own requests (one JSON line per request, one reply line) in niri's shapes
(niri-ipc/src/lib.rs at v26.04), and private {"Fake": {...}} requests from the fakes. It supports only
what the tests need:
- Requests: "Version", "Outputs", "Workspaces", "Windows", "FocusedOutput", "FocusedWindow", "Casts",
  "EventStream", and the actions MoveWindowToWorkspace, SetWorkspaceName, UnsetWorkspaceName and CloseWindow.
  Every other action is refused and recorded in `forbidden`.
- Like niri, an action replies {"Ok":"Handled"} even when it did nothing (an unknown reference, a duplicate
  name), and it never reuses a workspace id: a workspace that becomes empty, unnamed and inactive, and isn't
  its output's last, is deleted.
- An output always ends in an empty workspace: a window landing on the last one appends a new one
  (src/layout/monitor.rs:583-586). Naming the last workspace appends one only on the focused output
  (src/layout/mod.rs:4546-4567).
- An index reference resolves on the focused output for set/unset-name and on the window's output for a move.
- A new lab window opens on `open_on`'s active workspace, focused if `open_focused` (the window rule's
  effect, or its absence on a single screen). Opening it also replaces that output's trailing empty
  workspace with a new id, as another client opening a window would: a workspace id read before the
  launch is stale by the time the window appears.
- Moving a focused window with focus:false hands focus back to the window focused before it.
- When an app launches, every lab window already open reports WindowOpenedOrChanged, as a title change
  does in niri (src/ipc/server.rs:719-731): the first lab-window event a new lab sees may be another lab's.
- For each "EventStream" request it notes which processes were alive (`streams_opened`), and for each
  launch the launched app's ancestry, so a test can tell whether a lab listened before it launched. niri
  registers a stream only once it has answered the request (src/ipc/server.rs:209-262).
- Frames: a cast delivers a new frame only once per `frame_period` seconds (niri draws a hidden window about
  once a second, src/niri.rs:189-192); a consumer's first frame is STALE seconds old.
- With `pair_workspaces` set, a "Workspaces" request waits up to that many seconds for a second one, so two
  labs placing at once read the same layout, as they could in niri without a lock.
"""

import json
import os
import socket
import struct
import threading
import time
import zlib
from pathlib import Path
from typing import Any

LAB_APP_ID = "dev.claude.lab"
# The lab window's frame in a cast: an 80x24 grid of 10x20 px cells at (8, 12), inside an 816x504 window.
WINDOW = (816, 504)
GRID = {"x": 8, "y": 12, "cell_w": 10, "cell_h": 20, "cols": 80, "rows": 24}
# A browser lab's page: innerWidth x innerHeight, and the screenshot captureScreenshot returns.
VIEWPORT = (800, 600)
# The relay's magenta marker as niri's cast delivers it: a few levels off rgb(255,0,255).
CAST_MAGENTA = (250, 4, 251)
STALE = 0.8  # how old a cast's first frame is, in seconds


def output_info(name, x):
    return {
        "name": name,
        "make": "Fake",
        "model": name,
        "serial": None,
        "physical_size": [600, 340],
        "modes": [{"width": 2560, "height": 1440, "refresh_rate": 60000, "is_preferred": True}],
        "current_mode": 0,
        "vrr_supported": False,
        "vrr_enabled": False,
        "logical": {"x": x, "y": 0, "width": 2560, "height": 1440, "scale": 1.0, "transform": "Normal"},
    }


def parent(pid):
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return None


def line_of(pid):
    """`pid` and its ancestors, nearest first."""
    out = [pid]
    while (pid := parent(pid)) and pid > 1:
        out.append(pid)
    return out


def alive():
    return {int(d) for d in os.listdir("/proc") if d.isdigit()}


def dead(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return True
    return state in "ZX"


class Desk:
    def __init__(self, path, outputs=("DP-1", "eDP-1")):
        self.path = str(path)
        self.lock = threading.RLock()
        self.next_id = 1
        self.next_window = 10
        self.outputs = {n: output_info(n, 2560 * i) for i, n in enumerate(outputs)}
        self.focused_output = outputs[0]
        self.ws = {n: [] for n in outputs}  # output -> its workspaces, in order
        self.active = {}  # output -> the id of its active workspace
        self.windows: dict[int, dict[str, Any]] = {}  # id -> {"id", "app_id", "pid", "ws", "state_dir"}
        self.focus = None
        self.focus_before = []  # the windows focus returns to, most recent last
        self.focus_log = []  # every window that was ever focused, in order
        self.requests = []  # (time, request) for every niri request, in order
        self.forbidden = []  # actions the lab must never send
        self.streams = []
        self.sessions = {}  # D-Bus session path -> {"window", "node", "started", "stream"}
        self.created = []  # every session path ever created
        self.stopped = []  # session paths, in the order they were stopped
        self.nodes = {}  # PipeWire node -> the window its cast records
        self.frames = {}  # seq -> {"drawn", "first", "node"}
        self.consumers = {}
        self.draws = []  # (time, pid, text) for what a fake Ghostty's terminal printed
        self.launches = []  # {"time", "app", "pid", "argv", "env"}
        self.opened = []  # every lab window that ever opened
        self.cdp = []  # (time, pid, method, params)
        self.ran = []  # (tool, argv) for tools the lab must never run
        self.gif_frames = []  # the cast frames each GIF was made of, by seq
        self.open_on = outputs[-1]
        self.open_focused = len(outputs) == 1
        self.ignore = set()  # action names to accept and silently skip
        self.focus_on_move = False
        self.streams_opened = []  # {"time", "line": the peer and its ancestors, "alive": every pid then}
        self.frame_period = 0.05
        self.pair_workspaces = 0.0
        self.pairing = threading.Condition()
        self.pair_waiting, self.pair_round = False, 0
        for i, name in enumerate(outputs):
            first = self.add_ws(name)
            self.active[name] = first["id"]
            self.add_ws(name)
            user = {"id": i + 1, "app_id": "com.mitchellh.ghostty" if i == 0 else "firefox", "pid": os.getpid(),
                    "ws": first["id"], "state_dir": None}  # fmt: skip
            self.windows[user["id"]] = user
        self.focus = 1
        self.focus_log.append(1)
        self.start_shape = self.shape()
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(self.path)
        self.listener.listen(64)
        self.closed = False
        threading.Thread(target=self.serve, daemon=True).start()

    # ---------- layout ----------

    def add_ws(self, output):
        ws = {"id": self.next_id, "name": None}
        self.next_id += 1
        self.ws[output].append(ws)
        return ws

    def find_ws(self, wsid):
        for out, lst in self.ws.items():
            for w in lst:
                if w["id"] == wsid:
                    return out, w
        return None, None

    def occupied(self, wsid):
        return any(w["ws"] == wsid for w in self.windows.values())

    def cleanup(self, output):
        lst = self.ws[output]
        keep = [w for i, w in enumerate(lst)
                if i == len(lst) - 1 or w["name"] or w["id"] == self.active[output] or self.occupied(w["id"])]  # fmt: skip
        self.ws[output] = keep

    def resolve(self, ref, output_for_index):
        if not isinstance(ref, dict) or len(ref) != 1:
            return None
        (how, value), = ref.items()  # fmt: skip
        if how == "Id":
            return self.find_ws(value)[1]
        if how == "Name":
            return next((w for lst in self.ws.values() for w in lst
                         if w["name"] and w["name"].casefold() == str(value).casefold()), None)  # fmt: skip
        if how == "Index" and output_for_index:
            lst = self.ws[output_for_index]
            return lst[value - 1] if 1 <= value <= len(lst) else None
        return None

    def set_focus(self, wid):
        if self.focus != wid:
            if self.focus is not None:
                self.focus_before.append(self.focus)
            self.focus = wid
            self.focus_log.append(wid)
            self.emit({"WindowFocusChanged": {"id": wid}})

    def reap(self):
        for wid, w in list(self.windows.items()):
            if w["app_id"] == LAB_APP_ID and dead(w["pid"]):
                self.remove_window(wid)

    def remove_window(self, wid):
        w = self.windows.pop(wid)
        if self.focus == wid:
            self.focus = next((f for f in reversed(self.focus_before) if f in self.windows), None)
        out, _ = self.find_ws(w["ws"])
        if out:
            self.cleanup(out)
        self.emit({"WindowClosed": {"id": wid}})
        self.emit_workspaces()

    def open_window(self, pid, app_id, state_dir):
        out = self.open_on
        lst = self.ws[out]
        target = self.active[out]
        wid = self.next_window
        self.next_window += 1
        self.windows[wid] = {"id": wid, "app_id": app_id, "pid": pid, "ws": target, "state_dir": state_dir}
        self.opened.append(wid)
        if lst[-1]["id"] == target:
            self.add_ws(out)
        last = self.ws[out][-1]
        if not last["name"] and not self.occupied(last["id"]) and last["id"] != self.active[out]:
            self.ws[out].pop()
            self.add_ws(out)
        if self.open_focused:
            self.set_focus(wid)
        self.emit({"WindowOpenedOrChanged": {"window": self.window_json(self.windows[wid])}})
        self.emit_workspaces()
        return wid

    def move(self, a):
        w = self.windows.get(a.get("window_id"))
        if w is None or "MoveWindowToWorkspace" in self.ignore:
            return
        src_out, _ = self.find_ws(w["ws"])
        target = self.resolve(a.get("reference"), src_out)
        if target is None or target["id"] == w["ws"]:
            return
        out, _ = self.find_ws(target["id"])
        w["ws"] = target["id"]
        if self.ws[out][-1]["id"] == target["id"]:
            self.add_ws(out)
        if a.get("focus") or self.focus_on_move:
            self.set_focus(w["id"])
        elif self.focus == w["id"]:
            back = next((f for f in reversed(self.focus_before) if f in self.windows and f != w["id"]), None)
            self.set_focus(back)
        self.cleanup(src_out)
        self.emit({"WindowOpenedOrChanged": {"window": self.window_json(w)}})
        self.emit_workspaces()

    def set_name(self, a):
        if "SetWorkspaceName" in self.ignore:
            return
        ws = self.resolve(a.get("workspace"), self.focused_output)
        name = a.get("name")
        taken = any(w["name"] and w["name"].casefold() == str(name).casefold() for lst in self.ws.values() for w in lst)
        if ws is None or taken:
            return
        ws["name"] = name
        if self.ws[self.focused_output][-1]["id"] == ws["id"]:
            self.add_ws(self.focused_output)
        self.emit_workspaces()

    def unset_name(self, a):
        ws = self.resolve(a.get("reference"), self.focused_output)
        if ws is None:
            return
        ws["name"] = None
        self.cleanup(self.find_ws(ws["id"])[0])
        self.emit_workspaces()

    def close_window(self, a):
        w = self.windows.get(a.get("id"))
        if w is None:
            return
        if w["app_id"] == LAB_APP_ID and w["pid"] > 1:
            try:
                os.kill(w["pid"], 15)
            except ProcessLookupError:
                pass
        self.remove_window(w["id"])

    # ---------- what niri reports ----------

    def window_json(self, w):
        return {
            "id": w["id"], "title": "lab", "app_id": w["app_id"], "pid": w["pid"], "workspace_id": w["ws"],
            "is_focused": self.focus == w["id"], "is_floating": False, "is_urgent": False,
            "layout": {"pos_in_scrolling_layout": [1, 1], "tile_size": list(WINDOW), "window_size": list(WINDOW),
                       "tile_pos_in_workspace_view": None, "window_offset_in_tile": [0, 0]},
            "focus_timestamp": None,
        }  # fmt: skip

    def workspaces_json(self):
        focused_ws = self.windows[self.focus]["ws"] if self.focus in self.windows else None
        out = []
        for name, lst in self.ws.items():
            for i, w in enumerate(lst):
                here = [x["id"] for x in self.windows.values() if x["ws"] == w["id"]]
                out.append({"id": w["id"], "idx": i + 1, "name": w["name"], "output": name, "is_urgent": False,
                            "is_active": self.active[name] == w["id"],
                            "is_focused": w["id"] == focused_ws if focused_ws else False,
                            "active_window_id": here[0] if here else None})  # fmt: skip
        return out

    def casts_json(self):
        return [{"stream_id": i, "session_id": i, "kind": "PipeWire", "target": {"Window": {"id": s["window"]}},
                 "is_dynamic_target": False, "is_active": True, "pid": None, "pw_node_id": s["node"]}
                for i, s in enumerate(self.sessions.values()) if s["started"]]  # fmt: skip

    def shape(self):
        """Each output's workspaces as (name, window app ids): what a lab must leave as it found it."""
        return {out: [(w["name"], sorted(x["app_id"] for x in self.windows.values() if x["ws"] == w["id"]))
                      for w in lst] for out, lst in self.ws.items()}  # fmt: skip

    def lab_windows(self):
        return [self.window_json(w) for w in self.windows.values() if w["app_id"] == LAB_APP_ID]

    def emit(self, event):
        line = (json.dumps(event) + "\n").encode()
        for s in list(self.streams):
            try:
                s.sendall(line)
            except OSError:
                self.streams.remove(s)

    def emit_workspaces(self):
        self.emit({"WorkspacesChanged": {"workspaces": self.workspaces_json()}})

    # ---------- the socket ----------

    def serve(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self.client, args=(conn,), daemon=True).start()

    def client(self, conn):
        f = conn.makefile("rb")
        try:
            for line in f:
                try:
                    req = json.loads(line)
                except ValueError:
                    conn.sendall(b'{"Err":"error parsing request"}\n')
                    continue
                if req == "Workspaces" and self.pair_workspaces:
                    self.pair()
                with self.lock:
                    self.reap()
                    if req == "EventStream":
                        self.requests.append((time.time(), req))
                        peer = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0]
                        self.streams_opened.append({"time": time.time(), "line": line_of(peer), "alive": alive()})
                        conn.sendall(b'{"Ok":"Handled"}\n')
                        conn.sendall((json.dumps({"WorkspacesChanged": {"workspaces": self.workspaces_json()}}) + "\n"
                                      + json.dumps({"WindowsChanged": {"windows": [self.window_json(w) for w in
                                                    self.windows.values()]}}) + "\n").encode())  # fmt: skip
                        self.streams.append(conn)
                        continue
                    reply = self.answer(req)
                conn.sendall((json.dumps(reply) + "\n").encode())
        except OSError:
            pass
        finally:
            with self.lock:
                if conn in self.streams:
                    self.streams.remove(conn)
            conn.close()

    def pair(self):
        """Hold this Workspaces request until a second one arrives or `pair_workspaces` seconds pass."""
        with self.pairing:
            if self.pair_waiting:
                self.pair_waiting = False
                self.pair_round += 1
                self.pairing.notify_all()
                return
            self.pair_waiting, mine = True, self.pair_round
            if not self.pairing.wait_for(lambda: self.pair_round != mine, timeout=self.pair_workspaces):
                self.pair_waiting = False

    def answer(self, req):
        if isinstance(req, dict) and "Fake" in req:
            return {"Ok": self.fake(req["Fake"])}
        self.requests.append((time.time(), req))
        simple = {
            "Version": lambda: {"Version": "26.04 (fake)"},
            "Outputs": lambda: {"Outputs": self.outputs},
            "Workspaces": lambda: {"Workspaces": self.workspaces_json()},
            "Windows": lambda: {"Windows": [self.window_json(w) for w in self.windows.values()]},
            "FocusedOutput": lambda: {"FocusedOutput": self.outputs[self.focused_output]},
            "FocusedWindow": lambda: {"FocusedWindow": self.window_json(self.windows[self.focus])
                                      if self.focus in self.windows else None},
            "Casts": lambda: {"Casts": self.casts_json()},
        }  # fmt: skip
        if isinstance(req, str) and req in simple:
            return {"Ok": simple[req]()}
        if not (isinstance(req, dict) and isinstance(req.get("Action"), dict) and len(req["Action"]) == 1):
            return {"Err": "error parsing request"}
        (name, a), = req["Action"].items()  # fmt: skip
        handlers = {"MoveWindowToWorkspace": self.move, "SetWorkspaceName": self.set_name,
                    "UnsetWorkspaceName": self.unset_name, "CloseWindow": self.close_window}  # fmt: skip
        if name not in handlers:
            self.forbidden.append(req)
            return {"Err": f"the fake niri refuses {name}"}
        if name == "MoveWindowToWorkspace" and "focus" not in a:
            return {"Err": "error parsing request"}
        handlers[name](a)
        return "Handled"

    # ---------- the fakes' side door ----------

    def fake(self, r):
        op = r["op"]
        if op == "launch":
            self.launches.append({"time": time.time(), "line": line_of(r["pid"]),
                                  **{k: r[k] for k in ("app", "pid", "argv", "env")}})  # fmt: skip
            for w in self.windows.values():
                if w["app_id"] == LAB_APP_ID:
                    self.emit({"WindowOpenedOrChanged": {"window": self.window_json(w)}})
            return None
        if op == "open":
            return self.open_window(r["pid"], r["app_id"], r.get("state_dir"))
        if op == "draw":
            self.draws.append((time.time(), r["pid"], r["text"]))
            return None
        if op == "cdp":
            self.cdp.append((time.time(), r["pid"], r["method"], r.get("params", {})))
            return None
        if op == "gif-frame":
            self.gif_frames.append(r["seq"])
            return None
        if op == "ran":
            self.ran.append((r["tool"], r["argv"]))
            return None
        return getattr(self, "cast_" + op.replace("-", "_"))(r)

    def cast_create(self, r):
        path = f"/org/gnome/Mutter/ScreenCast/Session/u{len(self.created) + 1}"
        self.sessions[path] = {"window": None, "node": None, "started": False, "stream": None}
        self.created.append(path)
        return path

    def cast_record(self, r):
        s = self.sessions.get(r["session"])
        if s is None or r["window"] not in self.windows:
            return {"error": "GDBus.Error:org.freedesktop.DBus.Error.Failed: Unknown window"}
        s["window"] = r["window"]
        s["stream"] = r["session"].replace("Session", "Stream")
        return s["stream"]

    def cast_start(self, r):
        s = self.sessions.get(r["session"])
        if s is None or s["window"] is None:
            return {"error": "GDBus.Error:org.freedesktop.DBus.Error.Failed: nothing to start"}
        s["started"] = True
        s["node"] = 101 + len(self.nodes)
        self.nodes[s["node"]] = s["window"]
        return "()"

    def cast_stop(self, r):
        if self.sessions.pop(r["session"], None) is None:
            return {"error": f"GDBus.Error:org.freedesktop.DBus.Error.UnknownObject: No such object {r['session']}"}
        self.stopped.append(r["session"])
        return "()"

    def cast_frame(self, r):
        s = next((s for s in self.sessions.values() if s["started"] and s["node"] == r["node"]), None)
        if s is None or s["window"] not in self.windows:
            return {"error": f"no PipeWire node {r['node']}"}
        now = time.time()
        tick = now - now % self.frame_period
        seen = self.consumers.get(r["consumer"])
        if seen is not None and seen >= tick:
            return {"seq": None}
        first = seen is None
        self.consumers[r["consumer"]] = tick
        seq = len(self.frames) + 1
        drawn = now - STALE if first else tick
        self.frames[seq] = {"drawn": drawn, "first": first, "node": r["node"]}
        state_dir = self.windows[s["window"]]["state_dir"]
        markers = bool(state_dir) and not (Path(state_dir) / "go").exists()
        return {"seq": seq, "markers": markers}

    def close(self):
        self.closed = True
        self.listener.close()
        for s in list(self.streams):
            s.close()
        Path(self.path).unlink(missing_ok=True)


def request(path, req):
    """One request to the Desk (or niri) at `path`; returns the decoded reply."""
    s = socket.socket(socket.AF_UNIX)
    s.connect(path)
    with s:
        s.sendall((json.dumps(req) + "\n").encode())
        return json.loads(s.makefile().readline())


# ---------- PNG, stdlib only ----------


def png(width, height, rows):
    """An 8-bit RGB PNG from `rows`, each `width * 3` bytes."""

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\0" + r for r in rows)
    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b"")


def stamp(seq):
    """The background colour that marks frame `seq`: its number in green and blue."""
    return (35, (seq >> 8) & 0xFF, seq & 0xFF)


def frame_png(seq, size, markers=False):
    w, h = size
    bg = bytes(stamp(seq)) * w
    rows = [bg] * h
    if markers:
        g = GRID
        for col, row in ((1, 1), (g["cols"], g["rows"])):
            x0, y0 = g["x"] + (col - 1) * g["cell_w"], g["y"] + (row - 1) * g["cell_h"]
            line = bg[: x0 * 3] + bytes(CAST_MAGENTA) * g["cell_w"] + bg[(x0 + g["cell_w"]) * 3 :]
            for y in range(y0, y0 + g["cell_h"]):
                rows[y] = line
    return png(w, h, rows)


def read_png(data):
    """(width, height, pixel(x, y) -> (r, g, b)) for an 8-bit RGB or RGBA PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i, idat = 8, b""
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i : i + 8])
        body = data[i + 8 : i + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if depth != 8 or ctype not in (2, 6):
                raise ValueError(f"unsupported PNG: depth {depth}, colour type {ctype}")
            bpp = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    raw, stride, rows, prev, p = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp), 0
    for _ in range(h):
        f, line = raw[p], bytearray(raw[p + 1 : p + 1 + stride])
        p += 1 + stride
        for x in range(stride if f else 0):
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], (prev[x - bpp] if x >= bpp else 0)
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, lambda x, y: tuple(rows[y][x * bpp : x * bpp + 3])


def seq_of(data):
    """Which frame a PNG shows, read from the background colour at its centre."""
    w, h, pixel = read_png(data)
    _, g, b = pixel(w // 2, h // 2)
    return (g << 8) | b
