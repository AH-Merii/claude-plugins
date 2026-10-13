#!/usr/bin/env python3
"""niri-screen-lab: Ghostty or Chromium labs, each on its own hidden niri workspace, that never take focus or the clipboard.

Run `lab.py -h` for the commands. See SKILL.md and reference.md next to this file.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import browser
import cast
import place

HERE = Path(__file__).resolve().parent
APP_ID = os.environ.get("SCREEN_LAB_APP_ID", "dev.claude.lab")
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "")
LABS = Path(RUNTIME) / "screen-lab"  # one folder per lab: state.json, feed, logs
# Profiles and downloads live on disk, not in the runtime dir (a tmpfs), one folder per lab.
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "niri-screen-lab"
# Values the lab needs that differ from Ghostty's defaults or the user's config.
GHOSTTY_FLAGS = [
    "--gtk-single-instance=false",
    "--confirm-close-surface=false",
    "--clipboard-write=deny",
    "--clipboard-read=deny",
    "--copy-on-select=false",
    "--desktop-notifications=false",
]
PACKAGES = {
    "niri": "niri",
    "ghostty": "ghostty",
    "gst-launch-1.0": "gstreamer gst-plugin-pipewire gst-plugin-va",
    "gdbus": "glib2",
    "ffmpeg": "ffmpeg",
    "gi": "python-gobject",
    "chromium": "chromium",
}
FLASH = (
    "Tell the user: the new lab window holds keyboard focus for about 50 ms before it moves to a hidden "
    "workspace; a key pressed then goes to the lab."
)
COSTS = (
    "typical costs: about 80-110 MiB per terminal lab, plus about 50 MiB per running recording; "
    "about 280-300 MiB per headless browser lab and about 340-460 MiB per windowed one"
)


class Refuse(Exception):
    pass


def install_hint(tool):
    pkg = PACKAGES.get(tool, tool)
    if os.path.exists("/usr/bin/pacman"):
        return f"ask the user to run: sudo pacman -S {pkg}"
    return f"ask the user to install {pkg} with their package manager"


def need(tool, why):
    if not shutil.which(tool):
        raise Refuse(f"{tool} is not installed ({why}); {install_hint(tool)}")
    return shutil.which(tool)


# ---------- checks ----------


def check_niri():
    need("niri", "the compositor the lab drives")
    if not os.environ.get("NIRI_SOCKET"):
        raise Refuse("not running inside a niri session (NIRI_SOCKET unset); the lab only works on niri")
    try:
        return f"niri {place.request('Version')}"
    except (OSError, ValueError, place.PlaceError) as e:
        raise Refuse(f"niri's socket did not answer: {e}")


def check_runtime():
    if not RUNTIME or not os.path.isdir(RUNTIME):
        raise Refuse("XDG_RUNTIME_DIR is unset or missing; state goes in $XDG_RUNTIME_DIR/screen-lab")
    return str(LABS)


def check_app_id():
    try:
        from gi.repository import Gio  # ty: ignore[unresolved-import]  # system PyGObject, absent in CI
    except ImportError:
        raise Refuse(f"python3 cannot import gi (PyGObject), needed to validate the app-id; {install_hint('gi')}")
    if not Gio.Application.id_is_valid(APP_ID):
        raise Refuse(
            f'"{APP_ID}" is not a valid GTK application id (needs 2+ dot-separated parts, e.g. dev.claude.lab);'
            " the app would ignore it and open the window on the user's focused screen"
        )
    return APP_ID


def memory():
    """What memory is free, and what labs typically cost: whether to open another is the agent's call."""
    m = re.search(r"^MemAvailable:\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.MULTILINE)
    have = f"MemAvailable {int(m.group(1)) // 1024} MiB" if m else "MemAvailable unknown"
    return f"{have}; {COSTS}"


def enabled_outputs():
    return {n: o for n, o in place.request("Outputs").items() if o.get("logical")}


def spare_output(outs):
    """The output the user isn't working on, out of two or more."""
    focused = (place.request("FocusedOutput") or {}).get("name")
    want = os.environ.get("SCREEN_LAB_OUTPUT")
    cands = [n for n in outs if n != focused]
    internal = [n for n in cands if n.startswith("eDP")]
    if want and want not in outs:
        raise Refuse(f"SCREEN_LAB_OUTPUT={want} is not an enabled output ({', '.join(outs)})")
    pick = want or (internal[:1] or (cands if len(cands) == 1 else [None]))[0]
    if pick is None:
        raise Refuse(
            f"cannot tell which output is spare ({', '.join(cands)}); ask the user, then set SCREEN_LAB_OUTPUT"
        )
    if pick == focused:
        raise Refuse(f"the user is working on {pick}; the lab needs a screen they are not focused on")
    return pick


def choose_output():
    """The output lab windows go to, and whether it is the only one (single-screen mode, which needs no rule)."""
    outs = enabled_outputs()
    if not outs:
        raise Refuse("niri reports no enabled output")
    if len(outs) == 1:
        return next(iter(outs)), True
    pick = spare_output(outs)
    rule_for(pick)
    return pick, False


# ---------- niri config: does a window rule send APP_ID to the spare output, unfocused? ----------

STRING = r'r(?P<h>#+)"(?:.|\n)*?"(?P=h)|"(?:\\.|[^"\\])*"'


def kdl_string(tok):
    m = re.fullmatch(r'r(#+)"((?:.|\n)*)"\1', tok)
    if m:
        return m.group(2)
    if tok.startswith('"'):
        return re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)), tok[1:-1])
    return tok


def strip_comments(text):
    """Blank out comments (keeping offsets) and return (code, skeleton); the skeleton also blanks strings."""
    code, skel, i, n = [], [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            code.append(" " * (j - i))
            skel.append(" " * (j - i))
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank = re.sub(r"[^\n]", " ", text[i:j])
            code.append(blank)
            skel.append(blank)
        elif (m := re.compile(STRING).match(text, i)) and (text[i] != "r" or i == 0 or not text[i - 1].isalnum()):
            j = m.end()
            code.append(text[i:j])
            skel.append(re.sub(r"[^\n]", "x", text[i:j]))
        else:
            j = i + 1
            code.append(text[i])
            skel.append(text[i])
        i = j
    return "".join(code), "".join(skel)


def config_files(path, seen=None):
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen or not path.is_file():
        return
    seen.add(path)
    code, _ = strip_comments(path.read_text())
    yield path, code
    for m in re.finditer(r"^\s*include\s+(" + STRING + ")", code, re.MULTILINE):
        yield from config_files(path.parent / os.path.expanduser(kdl_string(m.group(1))), seen)


def node_props(line):
    return {m.group(1): kdl_string(m.group(2)) for m in re.finditer(r"([\w-]+)=(" + STRING + r"|\S+)", line)}


def matches(props):
    """True if a match/exclude node certainly matches a new lab window; None if it depends on more than app-id."""
    if "app-id" not in props or not re.search(props["app-id"], APP_ID):
        return False
    return True if set(props) == {"app-id"} else None


def window_rules():
    root = Path(
        os.environ.get("NIRI_CONFIG")
        or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "niri/config.kdl"
    )
    for path, code in config_files(root):
        _, skel = strip_comments(code)
        for m in re.finditer(r"(/-\s*)?\bwindow-rule\s*\{", skel):
            depth, j = 1, m.end()
            while depth and j < len(skel):
                depth += {"{": 1, "}": -1}.get(skel[j], 0)
                j += 1
            if m.group(1):
                continue
            nodes = [
                n.strip()
                for n in re.split(r"[\n;]", code[m.end() : j - 1])
                if n.strip() and not n.strip().startswith("/-")
            ]
            yield path, nodes


def rule_for(output):
    on_output = focused = None
    for _, nodes in window_rules():
        match = [matches(node_props(n)) for n in nodes if n.startswith("match ")]
        exclude = [matches(node_props(n)) for n in nodes if n.startswith("exclude ")]
        if (match and True not in match) or any(e is not False for e in exclude):
            continue
        for n in nodes:
            if n.startswith("open-on-output"):
                on_output = kdl_string(n.split(None, 1)[1])
            elif n.startswith("open-focused"):
                focused = n.split()[1:2] == ["true"]
    o = enabled_outputs().get(output, {})
    names = {output.casefold(), f"{o.get('make')} {o.get('model')} {o.get('serial') or 'Unknown'}".casefold()}
    snippet = (
        f'  window-rule {{\n    match app-id=r#"^{re.escape(APP_ID)}$"#\n'
        f'    open-on-output "{output}"\n    open-focused false\n  }}'
    )
    if on_output is None or on_output.casefold() not in names or focused is not False:
        got = f"open-on-output {on_output!r}, open-focused {focused}"
        raise Refuse(
            f"no niri window rule sends app-id {APP_ID} to {output} unfocused (found: {got}). "
            f"Ask the user to add this to their niri config (the output name is specific to their setup; "
            f"niri reloads it on save, check with `niri validate`):\n{snippet}"
        )
    return f"app-id {APP_ID} -> {on_output}, open-focused false"


# ---------- labs and their state ----------


def lab_dir(lab_id):
    return LABS / lab_id


def load(lab_id):
    try:
        return json.loads((lab_dir(lab_id) / "state.json").read_text())
    except (OSError, ValueError):
        return None


def save(st):
    tmp = lab_dir(st["id"]) / "state.tmp"
    tmp.write_text(json.dumps(st))
    tmp.replace(tmp.with_name("state.json"))


def new_lab():
    """A fresh lab id and its folder. Letters only, so an id never reads as a pid."""
    LABS.mkdir(mode=0o700, exist_ok=True)
    while True:
        lab_id = "".join(secrets.choice("bcdfghjkmnpqrstvwxz") for _ in range(5))
        with contextlib.suppress(FileExistsError):
            lab_dir(lab_id).mkdir(mode=0o700)
            return lab_id


def started(pid):
    """When process `pid` started, in clock ticks after boot (field 22 of /proc/PID/stat); None once it has exited."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return None
    return None if fields[0] in "ZX" else int(fields[19])


def launched(pid):
    """How the state records a process the lab started: a pid alone could name a later process that reused it."""
    return {"pid": pid, "started": started(pid)}


def alive(proc):
    """True while `proc`, as launched() recorded it, still runs. A record without a start time can't be verified,
    so it counts as gone: the lab never treats as its own, or signals, a process it can't tell it started."""
    if not (isinstance(proc, dict) and isinstance(proc.get("pid"), int) and proc["pid"] > 1):
        return False
    return proc.get("started") is not None and started(proc["pid"]) == proc["started"]


def alive_pid(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def session():
    """The Claude session running this command: its claude process id, or None outside Claude Code."""
    pid = os.environ.get("CLAUDE_PID", "")
    return int(pid) if pid.isdigit() else None


def check_owner(st):
    """A running lab belongs to the session that started it, until that session ends."""
    owner = st.get("owner")
    if alive(st) and owner and owner != session() and alive_pid(owner):
        raise Refuse(
            f"lab {st['id']} belongs to another Claude session (claude pid {owner}); try again later, or ask the user"
        )


def valid_id(lab_id):
    if not re.fullmatch(r"[\w-]+", lab_id):
        raise Refuse(f"no lab {lab_id!r}: a lab id is letters only; `lab.py list` shows the labs")
    return lab_id


def kind(st):
    return st.get("kind", "terminal")


@contextlib.contextmanager
def placement_lock():
    """One global lock around the sweep, the launch and the placement, so two labs never take the same workspace."""
    check_runtime()  # else LABS is relative, and the sweep would delete folders in the working directory
    LABS.mkdir(mode=0o700, exist_ok=True)
    with open(LABS / "lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


# ---------- cast sessions: each one is a file in the lab's casts/ folder, so none is lost to a race ----------


def open_cast(st):
    """A new ScreenCast session, recorded in the lab's state before it can record anything."""
    path = cast.create()
    casts = lab_dir(st["id"]) / "casts"
    casts.mkdir(exist_ok=True)
    (casts / path.rsplit("/", 1)[-1]).write_text(path)
    return path


def close_cast(st, path):
    cast.stop(path)
    (lab_dir(st["id"]) / "casts" / path.rsplit("/", 1)[-1]).unlink(missing_ok=True)


def lab_casts(st):
    folder = lab_dir(st["id"]) / "casts"
    return [f.read_text() for f in folder.iterdir()] if folder.is_dir() else []


# ---------- teardown and the sweep ----------


def end(proc, sig=signal.SIGTERM, grace=5.0):
    """Signal a process the lab started, if it still runs, and wait for it; SIGKILL once `grace` runs out."""
    if not alive(proc):
        return
    os.kill(proc["pid"], sig)
    deadline = time.monotonic() + grace
    while alive(proc) and time.monotonic() < deadline:
        time.sleep(0.05)
    if alive(proc):
        os.kill(proc["pid"], signal.SIGKILL)


def window_gone(st, timeout=5.0):
    deadline = time.monotonic() + timeout
    while place.window_of(st["pid"]):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def teardown(st):
    """End every process lab `st` started, stop its casts, give back its workspace, and delete its state and
    profile. Returns False if its app had already exited."""
    up = alive(st)
    end(st.get("rec"), signal.SIGINT if kind(st) == "terminal" else signal.SIGTERM)
    end(st.get("keeper"))
    # End the app itself: closing Ghostty's window through niri leaves a "close running process?" dialog.
    end(st)
    closed = not (up and st.get("window")) or window_gone(st)
    for path in lab_casts(st):
        close_cast(st, path)
    if st.get("workspace"):
        with contextlib.suppress(OSError, place.PlaceError):
            place.unname(st["id"])
    shutil.rmtree(CACHE / st["id"], ignore_errors=True)
    shutil.rmtree(lab_dir(st["id"]), ignore_errors=True)
    if not closed:
        raise Refuse(f"lab {st['id']}'s window is still open; tell the user")
    return up


def sweep():
    """Tear down every lab whose app has exited, whichever session started it. Call it under placement_lock."""
    for folder in LABS.iterdir() if LABS.is_dir() else ():
        if not folder.is_dir():
            continue
        st = load(folder.name)
        if st is None:  # a launch that never got as far as its state; it held the lock, so it is over
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(CACHE / folder.name, ignore_errors=True)
        elif not alive(st):
            with contextlib.suppress(Refuse, cast.CastError):
                teardown(st)


# ---------- opening a lab ----------


def clean_env():
    """The environment of a lab's app. No CLAUDE* variables, so a lab `claude` runs as a fresh session; no tmux
    ones, which would hide images; and no activation token, which would let the app take the user's focus."""
    drop = {"TMUX", "TMUX_PANE", "XDG_ACTIVATION_TOKEN", "DESKTOP_STARTUP_ID"}
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("CLAUDE") and k != "CLAUDE_CONFIG_DIR") and k not in drop
    }


def spawn(argv, log, **kw):
    """Start a detached process that writes to `log`; returns its launched() record."""
    with open(log, "w") as f:
        p = subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=f, stderr=f, **kw)
    return launched(p.pid)


def pre_launch(app, why, windowed=True):
    """The checks before a lab opens. Returns the output its window goes to, or None for a headless lab."""
    check_runtime()
    check_niri()
    need(app, why)
    print(memory(), file=sys.stderr)
    if not windowed:
        return None
    check_app_id()
    output, single = choose_output()
    if single:
        print(FLASH, file=sys.stderr)
    return output


def open_lab(kind_, build, output, cwd=None):
    """Sweep dead labs, then launch a new one and, with an output, give its window a hidden workspace there.

    All under the placement lock. `build(lab_id)` returns the app's argv, extra state and the variables its
    environment changes. Returns the state."""
    with placement_lock():
        sweep()
        lab_id = new_lab()
        try:
            argv, extra, env = build(lab_id)
            # Listen before launching, so the window's opening can't be missed.
            events = place.Events() if output else None
        except BaseException:
            shutil.rmtree(lab_dir(lab_id), ignore_errors=True)
            shutil.rmtree(CACHE / lab_id, ignore_errors=True)
            raise
        try:
            app = spawn(argv, lab_dir(lab_id) / f"{kind_}.log", env=clean_env() | env, cwd=cwd)
            st = {"id": lab_id, "kind": kind_, **app, "output": output, "owner": session(), **extra}
            save(st)
            if events:
                hide(st, events, output)
        finally:
            if events:
                events.close()
    return st


def hide(st, events, output):
    """Move the lab's new window to a workspace of its own on `output`, unfocused, and check it got there.

    On any failure, close the window, unname the workspace and refuse."""
    try:
        w = events.window_opened(APP_ID, st["pid"])
        if w is None:
            raise place.PlaceError(f"no {APP_ID} window of pid {st['pid']} appeared")
        st["window"], st["workspace"] = w["id"], place.workspace_name(st["id"])
        save(st)
        target = place.hide(w["id"], output, st["id"])
        w = place.check_hidden(w["id"], target["id"], st["id"])
    except (OSError, ValueError, place.PlaceError) as e:
        with contextlib.suppress(Refuse, OSError, place.PlaceError, cast.CastError):
            teardown(st)
        raise Refuse(f"aborted and closed the lab: {e}. If its window showed on the user's screen, tell them")
    st["window_size"] = w["layout"]["window_size"]
    save(st)


def announce(st):
    """Print the new lab's id, which every later command takes as `--lab`, and where it is."""
    print(f"lab {st['id']}")
    print(json.dumps({k: st.get(k) for k in ("kind", "pid", "window", "output", "workspace", "grid")}))


def cmd_start(a, _st=None):
    if not a.cmd:
        raise Refuse("usage: lab.py start [--cwd DIR] -- CMD [ARGS...]")
    output = pre_launch("ghostty", "the terminal under test")
    need("gdbus", "capture through niri's ScreenCast service")
    need("gst-launch-1.0", "decoding the lab window's cast")
    cwd = os.path.abspath(a.cwd)

    def build(lab_id):
        folder = lab_dir(lab_id)
        os.mkfifo(folder / "feed", 0o600)
        relay = [sys.executable, str(HERE / "relay.py"), str(folder), *a.cmd]
        ghostty = ["ghostty", f"--class={APP_ID}", *GHOSTTY_FLAGS, f"--working-directory={cwd}", "-e", *relay]
        return ghostty, {"cmd": a.cmd}, {}

    st = open_lab("terminal", build, output, cwd=cwd)
    st["grid"] = measure_grid(st)
    save(st)
    (lab_dir(st["id"]) / "go").touch()
    announce(st)
    if not st["grid"]:
        print("warning: could not measure the grid; `cell` and `--crop` are unavailable", file=sys.stderr)


def cmd_browse(a, _st=None):
    output = pre_launch("chromium", "the browser under test", windowed=a.window)

    def build(lab_id):
        profile = CACHE / lab_id / "profile"
        browser.prepare_profile(profile, CACHE / lab_id / "downloads")
        # Headless, Chromium's default window gave a 780x493 viewport, which most sites lay out as a tablet.
        mode = [] if a.window else ["--headless=new", "--window-size=1280,800"]
        argv = ["chromium", f"--class={APP_ID}", f"--user-data-dir={profile}", *browser.CHROMIUM_FLAGS, *mode]
        # Chromium's singleton socket goes in TMPDIR: a long one is too long to bind, and a stopped lab would
        # leave its folders behind. The lab's own folder is short and goes with the lab.
        tmp = lab_dir(lab_id) / "tmp"
        tmp.mkdir(mode=0o700)
        return [*argv, "about:blank"], {"profile": str(profile)}, {"TMPDIR": str(tmp)}

    st = open_lab("browser", build, output)
    mode_name = "windowed" if a.window else "headless"
    try:
        st["port"] = browser.devtools_port(st["profile"])
        st["keeper"] = spawn(
            [sys.executable, str(HERE / "browser.py"), "keep", str(lab_dir(st["id"])), str(st["port"]), mode_name],
            lab_dir(st["id"]) / "keeper.log",
        )
        save(st)
        with page(st) as cdp:
            browser.navigate(cdp, a.url)
    except (browser.CDPError, OSError) as e:
        teardown(st)
        raise Refuse(f"aborted and closed lab {st['id']}: {e}")
    announce(st)


# ---------- the terminal grid ----------


def term_size(st):
    """The relay's terminal size: (cols, rows, xpixel, ypixel)."""
    return tuple(map(int, (lab_dir(st["id"]) / "size").read_text().split()[:4]))


def window_frame(st):
    """A fresh PNG of the lab window, from a cast session of its own that is stopped again afterwards."""
    path = open_cast(st)
    try:
        node = cast.record(path, st["window"])
        with tempfile.TemporaryDirectory(dir=lab_dir(st["id"])) as tmp:
            return cast.grab(node, tmp)
    finally:
        close_cast(st, path)


def grid_in(frame, size):
    """Where the relay's two magenta marker cells put the grid in `frame`, or None if they aren't there."""
    cols, rows, xpx, _ = size
    found = cast.magenta(frame)
    if not found:
        return None
    x0, y0, x1, y1, count = found
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    # Two cell-sized blocks and nothing else, or something else on screen fooled us.
    if not (0.8 < count / (2 * cw * ch) < 1.2) or (xpx and abs(cw - xpx / cols) > 1):
        return None
    return {"x": x0, "y": y0, "cell_w": round(cw, 3), "cell_h": round(ch, 3), "cols": cols, "rows": rows}


def measure_grid(st):
    """Measure the grid in a cast frame while the relay shows its markers; None if it can't be measured."""
    for _ in range(50):
        if (lab_dir(st["id"]) / "size").exists():
            break
        time.sleep(0.1)
    try:
        for _ in range(3):
            if found := grid_in(window_frame(st), term_size(st)):
                return found
    except (OSError, ValueError, cast.CastError) as e:
        print(f"warning: {e}", file=sys.stderr)
    return None


def grid(st):
    g = st.get("grid")
    if not g:
        raise Refuse("the grid was not measured at start; pixel-to-cell mapping is unavailable")
    w = place.window_of(st["pid"])
    if w and w["layout"]["window_size"] != st.get("window_size"):
        raise Refuse("the lab window was resized since the grid was measured; restart the lab to remeasure")
    cols, rows = term_size(st)[:2]
    if (cols, rows) != (g["cols"], g["rows"]):
        raise Refuse(
            f"the terminal is now {cols}x{rows}, not the measured {g['cols']}x{g['rows']}; restart the lab to remeasure"
        )
    return g


# ---------- input ----------


@contextlib.contextmanager
def page(st):
    """A DevTools connection to the lab's page tab."""
    cdp = browser.CDP(browser.endpoints(st["port"], "page"))
    try:
        yield cdp
    finally:
        cdp.close()


def input_page(st):
    """page(), for commands that act on the page: refused while a windowed lab's window has keyboard focus. niri
    lets only the focused client set the clipboard, so an unfocused lab can't write it whatever a page does.
    A headless lab has no window to focus. Any of its windows counts: a popup the page opened has the same pid."""
    if st.get("window") and any(w["is_focused"] for w in place.windows_of(st["pid"])):
        raise Refuse(
            f"lab {st['id']}'s window has focus, so a page could write the clipboard; "
            "ask the user to focus another window, then retry"
        )
    return page(st)


def browser_lab(st, command):
    if kind(st) != "browser":
        raise Refuse(f"`{command}` needs a browser lab; open one with `lab.py browse URL`")
    return st


def feed(st, data):
    try:
        fd = os.open(lab_dir(st["id"]) / "feed", os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        raise Refuse(f"lab {st['id']}'s relay is not reading its feed")
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def cmd_open(a, st):
    with input_page(browser_lab(st, "open")) as cdp:
        browser.navigate(cdp, a.url)


def cmd_js(a, st):
    with input_page(browser_lab(st, "js")) as cdp:
        print(json.dumps(browser.evaluate(cdp, a.expression)))


def unescape(text):
    """printf-style: \\e \\xHH \\NNN \\n \\r \\t \\\\ \\uXXXX."""
    simple = {"e": "\x1b", "n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "\\": "\\", '"': '"', "'": "'"}

    def rep(m):
        s = m.group(1)
        if s[0] in "xu":
            return chr(int(s[1:], 16))
        if s[0].isdigit():
            return chr(int(s, 8))
        return simple.get(s, "\\" + s)

    return re.sub(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[0-7]{1,3}|.)", rep, text).encode()


KEYS = {
    "enter": "\r",
    "esc": "\x1b",
    "tab": "\t",
    "backspace": "\x7f",
    "space": " ",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pgup": "\x1b[5~",
    "pgdn": "\x1b[6~",
    "delete": "\x1b[3~",
    "shift-tab": "\x1b[Z",
    "shift-enter": "\x1b[13;2u",
}


def key_bytes(name):
    if name in KEYS:
        return KEYS[name].encode()
    if m := re.fullmatch(r"ctrl-([a-z@\[\\\]^_])", name):
        return bytes([ord(m.group(1).upper()) & 0x1F])
    if m := re.fullmatch(r"alt-(.)", name):
        return b"\x1b" + m.group(1).encode()
    raise Refuse(f"unknown key {name}; known: {', '.join(KEYS)}, ctrl-X, alt-X (or use `keys` with raw escapes)")


def cmd_keys(a, st):
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.type_text(cdp, unescape(a.text).decode())
        return
    feed(st, unescape(a.text))


def cmd_key(a, st):
    if kind(st) == "browser":
        with input_page(st) as cdp:
            for name in a.names:
                try:
                    browser.press(cdp, name)
                except ValueError as e:
                    raise Refuse(str(e))
                time.sleep(a.delay)
        return
    for name in a.names:
        feed(st, key_bytes(name))
        time.sleep(a.delay)


def sgr(button, col, row, final="M"):
    return f"\x1b[<{button};{col};{row}{final}".encode()


def cmd_hover(a, st):
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.mouse(cdp, "mouseMoved", a.col, a.row)
        return
    feed(st, sgr(35, a.col, a.row))


BUTTONS = {"left": 0, "middle": 1, "right": 2}


def cmd_click(a, st):
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.mouse(cdp, "mouseMoved", a.col, a.row)
            browser.mouse(cdp, "mousePressed", a.col, a.row, a.button, 1)
            browser.mouse(cdp, "mouseReleased", a.col, a.row, a.button, 1)
        return
    b = BUTTONS[a.button]
    feed(st, sgr(35, a.col, a.row))
    time.sleep(0.05)
    feed(st, sgr(b, a.col, a.row))
    time.sleep(0.05)
    feed(st, sgr(b, a.col, a.row, "m"))


def cmd_scroll(a, st):
    if kind(st) == "browser":
        with input_page(st) as cdp:
            dy = (-100 if a.direction == "up" else 100) * a.count
            browser.mouse(cdp, "mouseWheel", a.col, a.row, deltaX=0, deltaY=dy)
        return
    for _ in range(a.count):
        feed(st, sgr(64 if a.direction == "up" else 65, a.col, a.row))
        time.sleep(0.03)


# ---------- looking at a lab ----------


def page_info(st):
    if kind(st) != "browser":
        return None
    with page(st) as cdp:
        return browser.evaluate(cdp, "({url: location.href, title: document.title})")


def cmd_info(a, st):
    w = st.get("window") and place.window_of(st["pid"])
    size = dict(zip(("cols", "rows", "xpixel", "ypixel"), term_size(st))) if kind(st) == "terminal" else None
    info = {
        "lab": st["id"],
        "kind": kind(st),
        "pid": st["pid"],
        "output": st.get("output"),
        "workspace": st.get("workspace"),
        "cmd": st.get("cmd"),
        "window": w and {k: w[k] for k in ("id", "app_id", "is_focused", "workspace_id", "output")},
        "size": size,
        "grid": st.get("grid"),
        "page": page_info(st),
        "recording": alive(st.get("rec")),
    }
    print(json.dumps(info, indent=1))


def page_shot(st):
    with page(st) as cdp:
        return browser.screenshot(cdp)


def page_point(st, x, y):
    """A pixel in a page screenshot -> the page's CSS pixel, which hover, click and scroll take."""
    with page(st) as cdp:
        css_w, css_h = browser.evaluate(cdp, "[innerWidth, innerHeight]")
        w, h = browser.png_size(browser.screenshot(cdp))
    if not (0 <= x < w and 0 <= y < h):
        raise Refuse(f"pixel ({x},{y}) is outside the page's {w}x{h} screenshot")
    return round(x * css_w / w), round(y * css_h / h)


def cmd_cell(a, st):
    if kind(st) == "browser":
        print(*page_point(st, a.x, a.y))
        return
    g = grid(st)
    x, y = (a.x, a.y) if a.crop else (a.x - g["x"], a.y - g["y"])
    col, row = int(x // g["cell_w"]) + 1, int(y // g["cell_h"]) + 1
    if not (x >= 0 and y >= 0 and 1 <= col <= g["cols"] and 1 <= row <= g["rows"]):
        raise Refuse(f"pixel ({a.x},{a.y}) is outside the terminal grid")
    print(col, row)


def grid_box(st):
    """The grid's pixels in a frame of the lab window: x, y, width, height."""
    g = grid(st)
    return g["x"], g["y"], g["cols"] * g["cell_w"], g["rows"] * g["cell_h"]


def cmd_shot(a, st):
    if kind(st) == "browser":
        data = page_shot(st)  # the viewport, with or without --crop: a page has nothing around it
    else:
        data = window_frame(st)
        if a.crop:
            data = cast.crop(data, *grid_box(st))
    out = os.path.abspath(a.file)
    Path(out).write_bytes(data)
    print(out)


# ---------- recording ----------


def rec_start(st, crop):
    """Start writing frames to the lab's rec/ folder: a page's screenshots polled through DevTools, or a terminal
    window's cast decoded by GStreamer. The recorder and any cast session are recorded in the state."""
    need("ffmpeg", "GIF conversion")
    if alive(st.get("rec")):
        raise Refuse(f"lab {st['id']} is already recording; `lab.py rec-stop FILE.gif --lab {st['id']}` first")
    folder = lab_dir(st["id"]) / "rec"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    rec = {"folder": str(folder), "crop": crop, "began": time.time()}
    if kind(st) == "browser":
        argv = [sys.executable, str(HERE / "browser.py"), "poll", str(st["port"]), str(folder)]
    else:
        rec["cast"] = open_cast(st)
        argv = cast.pipeline(cast.record(rec["cast"], st["window"]), folder)
    st["rec"] = {**rec, **spawn(argv, lab_dir(st["id"]) / "rec.log")}
    save(st)


def rec_frames(st, rec):
    """Stop the recorder and its cast session; returns the frames it wrote, a cast's stale first one dropped."""
    end(rec, signal.SIGINT if rec.get("cast") else signal.SIGTERM)
    if rec.get("cast"):
        close_cast(st, rec["cast"])
    got = cast.frames(rec["folder"])
    return got[1:] if rec.get("cast") else got


def rec_stop(st, out, fps, width):
    rec = st.pop("rec", None)
    save(st)
    if not rec:
        raise Refuse(f"lab {st['id']} is not recording")
    got = rec_frames(st, rec)
    if not got:
        shutil.rmtree(rec["folder"], ignore_errors=True)
        raise Refuse("the recording holds no frames; take a `shot` instead")
    rate = max(0.5, len(got) / max(0.1, time.time() - rec["began"]))
    box = (
        "crop={2:.0f}:{3:.0f}:{0:.0f}:{1:.0f},".format(*grid_box(st)) if rec["crop"] and kind(st) == "terminal" else ""
    )
    vf = (
        f"{box}fps={fps},scale='min({width},iw)':-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5"
    )
    out = os.path.abspath(out)
    first = got[0].stem[1:]
    pattern = str(Path(rec["folder"]) / "f%05d.png")
    ff = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-framerate", f"{rate:.3f}", "-start_number", str(int(first)),
         "-i", pattern, "-vf", vf, "-loop", "0", out],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    shutil.rmtree(rec["folder"], ignore_errors=True)
    if ff.returncode != 0:
        raise Refuse(f"ffmpeg could not make the GIF: {(ff.stderr.strip().splitlines() or ['no output'])[-1]}")
    print(out, f"{os.path.getsize(out) // 1024} KiB")


def first_frame(st, timeout=10.0):
    """Wait until the recorder has written a frame, so a gif's seconds count from the first one."""
    deadline = time.monotonic() + timeout
    while not cast.frames(st["rec"]["folder"]) and time.monotonic() < deadline:
        time.sleep(0.05)


def cmd_gif(a, st):
    rec_start(st, a.crop)
    first_frame(st)
    time.sleep(a.seconds)
    rec_stop(load(st["id"]), a.file, a.fps, a.width)


def cmd_rec_start(a, st):
    rec_start(st, a.crop)
    print(f"recording; run `lab.py rec-stop FILE.gif --lab {st['id']}` to finish")


def cmd_rec_stop(a, st):
    rec_stop(st, a.file, a.fps, a.width)


# ---------- every lab, and ending one ----------


def cmd_list(a, _st=None):
    """Every lab, from every session, after sweeping the dead ones."""
    with placement_lock():
        sweep()
    labs = [st for f in sorted(LABS.iterdir()) if f.is_dir() and (st := load(f.name))]
    if not labs:
        print("no labs")
        return
    print("LAB    KIND      OWNER                 OUTPUT  WORKSPACE         APP")
    for st in labs:
        owner = st.get("owner")
        who = f"{owner} ({'live' if owner and alive_pid(owner) else 'ended'})" if owner else "-"
        cols = (st["id"], kind(st), who, st.get("output") or "-", st.get("workspace") or "-")
        print("{:<6} {:<9} {:<21} {:<7} {:<17}".format(*cols), "alive" if alive(st) else "exited")


def cmd_stop(a, st):
    print("stopped" if teardown(st) else "the lab had already exited; cleared its state")


def cmd_preflight(a, _st=None):
    ok = True

    def item(name, fn):
        nonlocal ok
        try:
            print(f"ok    {name}: {fn()}")
        except Refuse as e:
            ok = False
            print(f"FAIL  {name}: {e}")

    item("niri", check_niri)
    item("output", output_check)
    item("app-id", check_app_id)
    item("ghostty", lambda: need("ghostty", "the terminal under test"))
    if a.browser:
        item("chromium", lambda: need("chromium", "the browser under test"))
    item("gdbus", lambda: need("gdbus", "terminal capture through niri's ScreenCast service"))
    item("gst-launch-1.0", lambda: need("gst-launch-1.0", "decoding a terminal lab's cast"))
    item("ffmpeg", lambda: need("ffmpeg", "GIF conversion"))
    item("runtime dir", check_runtime)
    print(f"info  memory: {memory()}")
    print("ready" if ok else "not ready: fix the FAIL lines (relay the ask-the-user ones), then rerun preflight")
    return 0 if ok else 1


def output_check():
    output, single = choose_output()
    if single:
        return f"{output}, the only screen: single-screen mode, no window rule needed; {FLASH}"
    return f"{output}, with its window rule; the user works on another screen"


# ---------- the command line ----------


def lab_parser(sub, name, fn, **kw):
    """A command that acts on one lab, named with a required `--lab ID`: there is no "the only lab" default,
    because sibling subagents share CLAUDE_PID and could pick each other's lab."""
    s = sub.add_parser(name, **kw)
    s.add_argument("--lab", required=True, metavar="ID", help="the lab's id, as `start`/`browse` printed it")
    s.set_defaults(fn=fn)
    return s


def recording_parsers(sub):
    helps = {"gif": "record SECONDS then write FILE.gif", "rec-start": "start recording",
             "rec-stop": "stop recording and write FILE.gif"}  # fmt: skip
    for name, fn in (("gif", cmd_gif), ("rec-start", cmd_rec_start), ("rec-stop", cmd_rec_stop)):
        s = lab_parser(sub, name, fn, help=helps[name])
        if name != "rec-start":
            s.add_argument("file")
        if name == "gif":
            s.add_argument("seconds", type=float)
        if name != "rec-stop":
            s.add_argument("--crop", action="store_true", help="terminal: just the grid")
        if name != "rec-start":
            s.add_argument("--fps", type=int, default=12)
            s.add_argument("--width", type=int, default=1200)


def mouse_parsers(sub):
    for name, fn in (("hover", cmd_hover), ("click", cmd_click)):
        s = lab_parser(sub, name, fn, help=f"mouse {name} at a 1-based cell (terminal) or a CSS pixel (browser)")
        s.add_argument("col", type=int, metavar="COL|X")
        s.add_argument("row", type=int, metavar="ROW|Y")
        if name == "click":
            s.add_argument("--button", choices=BUTTONS, default="left")
    s = lab_parser(sub, "scroll", cmd_scroll, help="mouse wheel at a cell (terminal) or a CSS pixel (browser)")
    s.add_argument("direction", choices=("up", "down"))
    s.add_argument("col", type=int, metavar="COL|X")
    s.add_argument("row", type=int, metavar="ROW|Y")
    s.add_argument("--count", type=int, default=1)


def opening_parsers(sub):
    s = sub.add_parser("preflight", aliases=["doctor"], help="check every prerequisite, and the memory free")
    s.add_argument("--browser", action="store_true", help="also check what `browse` needs")
    s.set_defaults(fn=cmd_preflight)
    sub.add_parser("list", help="every lab, from every session").set_defaults(fn=cmd_list)
    s = sub.add_parser("start", help="open a terminal lab running CMD; prints `lab ID`")
    s.add_argument("--cwd", default=os.getcwd())
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("browse", help="open a browser lab (headless Chromium) at URL; prints `lab ID`")
    s.add_argument("url", nargs="?", default="about:blank")
    s.add_argument("--window", action="store_true", help="a real Chromium window on a hidden workspace")
    s.set_defaults(fn=cmd_browse)


def parser():
    p = argparse.ArgumentParser(prog="lab.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    opening_parsers(sub)
    lab_parser(sub, "keys", cmd_keys, help="feed raw bytes (printf escapes: \\e \\r \\x15 ...)").add_argument("text")
    s = lab_parser(sub, "key", cmd_key, help="named keys: enter esc tab up ctrl-u alt-x ...")
    s.add_argument("names", nargs="+")
    s.add_argument("--delay", type=float, default=0.05)
    lab_parser(sub, "open", cmd_open, help="browser lab: go to URL").add_argument("url")
    s = lab_parser(sub, "js", cmd_js, help="browser lab: evaluate a JavaScript expression in the page, print its JSON")
    s.add_argument("expression")
    mouse_parsers(sub)
    lab_parser(sub, "info", cmd_info, help="the lab's window, size and grid as JSON")
    s = lab_parser(sub, "cell", cmd_cell, help="screenshot pixel -> col row (terminal) or page x y (browser)")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s.add_argument("--crop", action="store_true", help="pixel is from a --crop screenshot")
    s = lab_parser(sub, "shot", cmd_shot, help="PNG of the lab window (--crop: the terminal grid) or the page")
    s.add_argument("file")
    s.add_argument("--crop", action="store_true")
    recording_parsers(sub)
    lab_parser(sub, "stop", cmd_stop, help="close the lab and clean up")
    return p


def addressed(a):
    """The lab `--lab` names, checked: refused if another live session owns it, or (but for `stop`) it isn't running."""
    check_runtime()
    if not re.fullmatch(r"[\w-]+", a.lab):
        raise Refuse(f"no lab {a.lab!r}; `lab.py list` shows the labs")
    st = load(a.lab)
    if st is None:
        raise Refuse(f"no lab {a.lab}; `lab.py list` shows the labs")
    check_owner(st)
    if a.command != "stop" and not alive(st):
        raise Refuse(f"no lab {a.lab} is running (its app has exited); `lab.py stop --lab {a.lab}` clears it")
    return st


def main():
    a = parser().parse_args()
    if getattr(a, "cmd", None) and a.cmd[0] == "--":
        a.cmd = a.cmd[1:]
    try:
        st = addressed(a) if hasattr(a, "lab") else None
        sys.exit(a.fn(a, st) or 0)
    except (Refuse, browser.CDPError, cast.CastError, place.PlaceError) as e:
        print(f"niri-screen-lab: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
