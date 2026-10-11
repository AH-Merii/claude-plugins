"""Run a command in a pty, passing the terminal through untouched and merging bytes from a FIFO into its input.

usage: relay.py STATE_DIR CMD [ARGS...]

Before the command starts, it paints a marker cell in two corners and waits for STATE_DIR/go,
so lab.py can measure the grid in a screenshot. Afterwards it keeps STATE_DIR/size
("cols rows xpixel ypixel") current, reads input from STATE_DIR/feed, and logs any OSC 52
clipboard writes from the command to STATE_DIR/osc52.log (Ghostty itself is told to deny them).
"""

import base64
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time
import tty

state, argv = sys.argv[1], sys.argv[2:]
sys.stderr = open(os.path.join(state, "relay.log"), "a", buffering=1)  # noqa: SIM115 -- stderr for the whole run
MARK = b"\x1b[48;2;255;0;255m \x1b[0m"
go = os.path.join(state, "go")
child = None
pid = None
marking = True


def winsize():
    return fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8)


def write_size(size):
    rows, cols, xpx, ypx = struct.unpack("HHHH", size)
    tmp = os.path.join(state, "size.tmp")
    with open(tmp, "w") as f:
        f.write(f"{cols} {rows} {xpx} {ypx}\n")
    os.replace(tmp, os.path.join(state, "size"))
    return rows, cols


def paint():
    rows, cols = write_size(winsize())
    os.write(1, b"\x1b[?25l\x1b[2J\x1b[H" + MARK + f"\x1b[{rows};{cols}H".encode() + MARK)


def resize(*_):
    # A forked child that has not exec'd yet must not touch the parent's pty.
    if pid == 0:
        return
    size = winsize()
    write_size(size)
    if child is None:
        if marking:
            paint()
        return
    fcntl.ioctl(child, termios.TIOCSWINSZ, size)
    os.kill(pid, signal.SIGWINCH)


saved = termios.tcgetattr(0)
tty.setraw(0)
signal.signal(signal.SIGWINCH, resize)
paint()
deadline = time.time() + 30
while not os.path.exists(go) and time.time() < deadline:
    time.sleep(0.05)
marking = False
rows, cols = struct.unpack("HHHH", winsize())[:2]
# Blank the markers before the reset: Ghostty's erase-display pushes them into scrollback instead.
os.write(1, f"\x1b[0m\x1b[1;1H \x1b[{rows};{cols}H \x1bc\x1b[3J".encode())

pid, child = pty.fork()
if pid == 0:
    signal.signal(signal.SIGWINCH, signal.SIG_DFL)
    # No display for the command: an app that copies through wl-copy or xclip would reach the user's clipboard.
    for k in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DISPLAY"):
        os.environ.pop(k, None)
    try:
        os.execvp(argv[0], argv)
    except OSError as e:
        print(f"screen-lab relay: cannot run {argv[0]}: {e}", file=sys.stderr)
        os._exit(127)
fcntl.ioctl(child, termios.TIOCSWINSZ, winsize())

osc52 = re.compile(rb"\x1b\]52;([^;\x07\x1b]*);([^\x07\x1b]*)(?:\x07|\x1b\\)")
tail = b""


def log_osc52(data):
    global tail
    buf = tail + data
    end = 0
    for m in osc52.finditer(buf):
        end = m.end()
        try:
            text = base64.b64decode(m.group(2)).decode("utf-8", "replace")
        except ValueError:
            text = "<undecodable>"
        with open(os.path.join(state, "osc52.log"), "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} target={m.group(1).decode()} {text!r}\n")
    # Keep an unterminated sequence for the next chunk.
    start = buf.rfind(b"\x1b]52;", end)
    tail = buf[start:][-1 << 20 :] if start >= 0 else b""


# Opened read-write so it never reads EOF when a writer closes.
feed = os.open(os.path.join(state, "feed"), os.O_RDWR | os.O_NONBLOCK)
try:
    while True:
        try:
            ready, _, _ = select.select([0, feed, child], [], [])
        except InterruptedError:
            continue
        if child in ready:
            try:
                data = os.read(child, 65536)
            except OSError:
                break
            if not data:
                break
            log_osc52(data)
            os.write(1, data)
        for src in (0, feed):
            if src in ready:
                os.write(child, os.read(src, 65536))
finally:
    termios.tcsetattr(0, termios.TCSAFLUSH, saved)
    os.waitpid(pid, 0)
