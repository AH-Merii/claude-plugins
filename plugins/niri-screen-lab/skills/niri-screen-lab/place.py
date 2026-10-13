"""niri's IPC socket, and how a lab window gets its own hidden workspace.

Every request goes over $NIRI_SOCKET as one JSON line with one reply line (niri-ipc/src/lib.rs). Workspaces are
referenced only by id or name: an index resolves against the focused output. niri answers {"Ok":"Handled"} even
when an action did nothing, and deletes a workspace that becomes empty and inactive, so every step re-queries.
"""

import json
import os
import socket
import time


class PlaceError(Exception):
    pass


def connect():
    """A socket connected to niri's IPC."""
    path = os.environ.get("NIRI_SOCKET")
    if not path:
        raise PlaceError("NIRI_SOCKET is unset, so niri can't be reached")
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(path)
    except OSError:
        s.close()
        raise
    return s


def request(req):
    """One request to niri; returns the value inside its {"Ok": ...} reply."""
    s = connect()
    with s:
        s.sendall((json.dumps(req) + "\n").encode())
        reply = json.loads(s.makefile().readline())
    if "Err" in reply:
        raise PlaceError(f"niri refused {json.dumps(req)}: {reply['Err']}")
    ok = reply["Ok"]
    return next(iter(ok.values())) if isinstance(ok, dict) and isinstance(req, str) else ok


def action(verb, /, **fields):
    request({"Action": {verb: fields}})


def workspaces():
    return request("Workspaces")


def windows():
    return request("Windows")


def windows_of(pid):
    """Every window whose client is `pid`: a browser's popups as well as its first window."""
    return [x for x in windows() if x["pid"] == pid]


def window_of(pid):
    """The window whose client is `pid`, with its workspace's output and name added; None if it has none."""
    w = next(iter(windows_of(pid)), None)
    if w:
        ws = next((x for x in workspaces() if x["id"] == w["workspace_id"]), {})
        w["output"], w["workspace"] = ws.get("output"), ws.get("name")
    return w


def workspace_name(lab_id):
    return f"claude-lab-{lab_id}"


class Events:
    """niri's event stream, opened before the lab launches so its window's opening can't be missed."""

    def __init__(self):
        self.sock = connect()
        self.sock.sendall(b'"EventStream"\n')
        self.lines = self.sock.makefile()
        reply = json.loads(self.lines.readline())
        if "Ok" not in reply:
            self.close()
            raise PlaceError(f"niri refused the event stream: {reply}")

    def window_opened(self, app_id, pid, timeout=10.0):
        """The first opened-or-changed window of `app_id` whose client is `pid`, or None after `timeout`."""
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            self.sock.settimeout(left)
            try:
                line = self.lines.readline()
            except TimeoutError:
                return None
            if not line:
                return None
            w = json.loads(line).get("WindowOpenedOrChanged", {}).get("window")
            if w and w["app_id"] == app_id and w["pid"] == pid:
                return w
        return None

    def close(self):
        self.sock.close()


def last_workspace(output):
    """The workspace with the highest idx on `output`: niri keeps it empty and unnamed."""
    return max((w for w in workspaces() if w["output"] == output), key=lambda w: w["idx"])


def hide(window_id, output, lab_id):
    """Move the window to `output`'s trailing workspace, unfocused, then name that workspace for the lab.

    Moving first: a window landing on the last workspace makes niri append a new empty one. Returns the workspace."""
    target = last_workspace(output)
    action("MoveWindowToWorkspace", window_id=window_id, reference={"Id": target["id"]}, focus=False)
    action("SetWorkspaceName", name=workspace_name(lab_id), workspace={"Id": target["id"]})
    return target


def check_hidden(window_id, workspace_id, lab_id):
    """The window, once it sits unfocused on its workspace, which carries the lab's name; else PlaceError."""
    w = next((x for x in windows() if x["id"] == window_id), None)
    ws = next((x for x in workspaces() if x["id"] == workspace_id), None)
    if w is None:
        raise PlaceError("the lab window closed")
    if w["workspace_id"] != workspace_id:
        raise PlaceError("niri did not move the lab window to its workspace")
    if ws is None or ws["name"] != workspace_name(lab_id):
        raise PlaceError("niri did not name the lab's workspace")
    if w["is_focused"]:
        raise PlaceError("the lab window has keyboard focus")
    return w


def unname(lab_id):
    """Drop the lab's workspace name; niri then removes the workspace once it is empty."""
    action("UnsetWorkspaceName", reference={"Name": workspace_name(lab_id)})
