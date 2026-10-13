"""Terminal capture: niri's org.gnome.Mutter.ScreenCast service records one window, GStreamer decodes it to PNG.

niri owns the service, so no portal or dialog is involved, and it records a window on a hidden workspace without
focusing it. A session outlives the process that created it, so the lab records every session path and stops each
one itself. Hidden windows draw about once a second (niri src/niri.rs:189-192); a consumer's first frame is old.
"""

import re
import struct
import subprocess
import time
import zlib
from pathlib import Path

import place

BUS = "org.gnome.Mutter.ScreenCast"
ROOT = "/org/gnome/Mutter/ScreenCast"
# The only decode that worked with niri's dmabuf frames (the multilab spike, section B).
DECODE = ["!", "vapostproc", "!", "video/x-raw,format=BGRx", "!", "videoconvert", "!", "video/x-raw,format=RGB",
          "!", "pngenc", "!"]  # fmt: skip


class CastError(Exception):
    pass


def gdbus(path, method, *args):
    r = subprocess.run(
        ["gdbus", "call", "--session", "--dest", BUS, "--object-path", path, "--method", method, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise CastError(f"{method.rsplit('.', 1)[-1]} failed: {r.stderr.strip()}")
    return r.stdout


def create():
    """A new ScreenCast session's object path."""
    m = re.search(r"'([^']+)'", gdbus(ROOT, f"{BUS}.CreateSession", "{}"))
    if m is None:
        raise CastError("CreateSession returned no session path")
    return m.group(1)


def nodes(window_id):
    return {c["pw_node_id"] for c in place.request("Casts")
            if c["target"].get("Window", {}).get("id") == window_id and c["pw_node_id"] is not None}  # fmt: skip


def record(session, window_id, timeout=5.0):
    """Record the window in `session` and start it; returns the new PipeWire node."""
    gdbus(session, f"{BUS}.Session.RecordWindow", f"{{'window-id': <uint64 {window_id}>}}")
    before = nodes(window_id)
    gdbus(session, f"{BUS}.Session.Start")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        new = nodes(window_id) - before
        if new:
            return new.pop()
        time.sleep(0.05)
    raise CastError("niri listed no PipeWire node for the lab window's cast")


def stop(session):
    """End a session; one that is already gone (niri ends a window's casts when it closes) is fine."""
    try:
        gdbus(session, f"{BUS}.Session.Stop")
    except CastError:
        pass


def pipeline(node, folder, count=0):
    """gst-launch-1.0 argv writing each frame of `node` to folder/f00000.png, f00001.png, ..."""
    src = ["pipewiresrc", f"path={node}", *([f"num-buffers={count}"] if count else [])]
    return ["gst-launch-1.0", "-q", "-e", *src, *DECODE, "multifilesink", f"location={folder}/f%05d.png"]


def frames(folder):
    return sorted(Path(folder).glob("f*.png"))


def grab(node, folder, timeout=15.0):
    """A frame of `node` drawn after this call began: the second one, since a cast's first frame is stale."""
    try:
        subprocess.run(pipeline(node, folder, 2), capture_output=True, timeout=timeout, check=True)
    except subprocess.TimeoutExpired:
        raise CastError(f"the cast delivered no fresh frame in {timeout:.0f}s")
    except subprocess.CalledProcessError as e:
        raise CastError(f"gst-launch-1.0 failed: {e.stderr.decode(errors='replace').strip()[-400:]}")
    got = frames(folder)
    if len(got) < 2:
        raise CastError("the cast delivered no fresh frame")
    return got[-1].read_bytes()


# ---------- PNG, stdlib only ----------


def unfilter(raw, width, height, bpp):
    """Undo PNG's per-row filters; returns the rows."""
    stride, rows, prev, p = width * bpp, [], bytearray(width * bpp), 0
    for _ in range(height):
        f, line = raw[p], bytearray(raw[p + 1 : p + 1 + stride])
        p += 1 + stride
        if f == 2:
            line = bytearray((x + y) & 255 for x, y in zip(line, prev))
        elif f:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b, c = prev[x], (prev[x - bpp] if x >= bpp else 0)
                line[x] = (line[x] + predict(f, a, b, c)) & 255
        rows.append(line)
        prev = line
    return rows


def predict(f, a, b, c):
    if f == 1:
        return a
    if f == 3:
        return (a + b) >> 1
    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_png(data):
    """(width, height, rows of RGB bytes) for an 8-bit RGB or RGBA PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise CastError("the frame is not a PNG")
    i, idat, head = 8, b"", None
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i : i + 8])
        body = data[i + 8 : i + 8 + n]
        if kind == b"IHDR":
            head = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    if head is None or head[2] != 8 or head[3] not in (2, 6):
        raise CastError(f"unsupported PNG header {head}")
    w, h, _, ctype = head
    bpp = 3 if ctype == 2 else 4
    rows = unfilter(zlib.decompress(idat), w, h, bpp)
    if bpp == 4:
        rows = [bytearray(b for i, b in enumerate(r) if i % 4 != 3) for r in rows]
    return w, h, rows


def write_png(width, height, rows):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def crop(data, x, y, w, h):
    width, height, rows = read_png(data)
    x, y = max(0, round(x)), max(0, round(y))
    w, h = min(round(w), width - x), min(round(h), height - y)
    return write_png(w, h, [r[x * 3 : (x + w) * 3] for r in rows[y : y + h]])


# The relay's magenta cells, a few levels off rgb(255,0,255) once niri's cast has converted them.
MAGENTA = re.compile(rb"[\xf0-\xff][\x00-\x10][\xf0-\xff]")


def magenta(data):
    """The magenta pixels in a frame: (x0, y0, x1, y1, count), or None."""
    _, _, rows = read_png(data)
    xs, ys, count = [], [], 0
    for y, row in enumerate(rows):
        found = [m.start() // 3 for m in MAGENTA.finditer(row) if m.start() % 3 == 0]
        if found:
            xs += [found[0], found[-1]]
            ys.append(y)
            count += len(found)
    if not ys:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1, count
