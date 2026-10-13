#!/usr/bin/env python3
"""niri-screen-lab: a real Ghostty or Chromium window on a spare niri output that never takes focus or the clipboard.

Run `lab.py -h` for the commands. See SKILL.md and reference.md next to this file.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import browser

HERE = Path(__file__).resolve().parent
APP_ID = os.environ.get("SCREEN_LAB_APP_ID", "dev.claude.lab")
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "")
STATE = Path(RUNTIME) / "screen-lab"
STATE_FILE = STATE / "state.json"
FEED = STATE / "feed"
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
    "grim": "grim",
    "wf-recorder": "wf-recorder",
    "ffmpeg": "ffmpeg",
    "gi": "python-gobject",
    "chromium": "chromium",
}
# The process a lab runs, by kind: `start` opens a terminal lab, `browse` a browser lab.
PROCESS = {"terminal": "ghostty", "browser": "chromium"}


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


def niri(*args):
    return json.loads(subprocess.check_output(["niri", "msg", "--json", *args]))


# ---------- checks ----------


def check_niri():
    need("niri", "the compositor the lab drives")
    if not os.environ.get("NIRI_SOCKET"):
        raise Refuse("not running inside a niri session (NIRI_SOCKET unset); the lab only works on niri")
    try:
        v = niri("version")
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        raise Refuse(f"niri msg failed: {e}")
    return f"niri {v.get('compositor', '?')}"


def check_runtime():
    if not RUNTIME or not os.path.isdir(RUNTIME):
        raise Refuse("XDG_RUNTIME_DIR is unset or missing; state goes in $XDG_RUNTIME_DIR/screen-lab")
    return str(STATE)


def check_app_id():
    try:
        from gi.repository import Gio  # ty: ignore[unresolved-import]  # system PyGObject, absent in CI
    except ImportError:
        raise Refuse(f"python3 cannot import gi (PyGObject), needed to validate the app-id; {install_hint('gi')}")
    if not Gio.Application.id_is_valid(APP_ID):
        raise Refuse(
            f'"{APP_ID}" is not a valid GTK application id (needs 2+ dot-separated parts, e.g. dev.claude.lab);'
            " Ghostty would ignore it and open the window on the user's focused screen"
        )
    return APP_ID


def enabled_outputs():
    return {n: o for n, o in niri("outputs").items() if o.get("logical")}


def spare_output():
    outs = enabled_outputs()
    if len(outs) < 2:
        raise Refuse(
            f"needs two enabled outputs, found {len(outs)} ({', '.join(outs) or 'none'}); "
            "ask the user to connect or enable a second screen to lend to the lab"
        )
    focused = (niri("focused-output") or {}).get("name")
    want = os.environ.get("SCREEN_LAB_OUTPUT")
    if want:
        if want not in outs:
            raise Refuse(f"SCREEN_LAB_OUTPUT={want} is not an enabled output ({', '.join(outs)})")
        pick = want
    else:
        cands = [n for n in outs if n != focused]
        internal = [n for n in cands if n.startswith("eDP")]
        if internal:
            pick = internal[0]
        elif len(cands) == 1:
            pick = cands[0]
        else:
            raise Refuse(
                f"cannot tell which output is spare ({', '.join(cands)}); ask the user, then set SCREEN_LAB_OUTPUT"
            )
    if pick == focused:
        raise Refuse(f"the user is working on {pick}; the lab needs a screen they are not focused on")
    return pick, outs[pick]


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


# ---------- state and the lab window ----------


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return None


def save_state(st):
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))


def alive(pid):
    try:
        comm = Path(f"/proc/{pid}/comm").read_text()
    except OSError:
        return False
    return any(name in comm for name in PROCESS.values())


def kind(st):
    return st.get("kind", "terminal")


def find_window(pid):
    """The lab window is found by Ghostty's pid, so a wrong app-id can never hide it."""
    for w in niri("windows"):
        if w["pid"] == pid:
            ws = {x["id"]: x for x in niri("workspaces")}.get(w["workspace_id"], {})
            w["output"] = ws.get("output")
            return w
    return None


def session():
    """The Claude session running this command: its claude process id, or None outside Claude Code."""
    pid = os.environ.get("CLAUDE_PID", "")
    return int(pid) if pid.isdigit() else None


def check_owner(st):
    """A running lab belongs to the session that started it, until that session ends."""
    owner = st.get("owner")
    if alive(st["pid"]) and owner and owner != session() and alive_pid(owner):
        raise Refuse(
            f"the lab belongs to another Claude session (claude pid {owner}) and only one lab runs at a time; "
            "try again later, or ask the user"
        )


@contextlib.contextmanager
def start_lock():
    """Serialises `start`, so two sessions can't both find the spare output free."""
    STATE.mkdir(mode=0o700, exist_ok=True)
    with open(STATE / "lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def running():
    st = load_state()
    if not st or not alive(st["pid"]):
        raise Refuse("no lab is running; use `lab.py start -- CMD...`")
    return st


def alone(st):
    """The whole spare output may be captured only when the lab window is alone on its visible workspace."""
    w = find_window(st["pid"])
    if not w:
        raise Refuse("the lab window is gone")
    ws = {x["id"]: x for x in niri("workspaces")}[w["workspace_id"]]
    if ws["output"] != st["output"]:
        raise Refuse(f"the lab window moved to {ws['output']}; refusing to capture the user's screen")
    if not ws["is_active"]:
        raise Refuse(f"the lab workspace is not the visible one on {st['output']} (the user switched); refusing")
    others = [x["app_id"] for x in niri("windows") if x["workspace_id"] == w["workspace_id"] and x["id"] != w["id"]]
    if others:
        raise Refuse(f"other windows share the lab workspace ({', '.join(map(str, others))}); refusing to capture them")
    if w["is_focused"]:
        print(
            "warning: the lab window has focus (pointer on the spare screen?); ask the user to move it away",
            file=sys.stderr,
        )
    return w


def global_rect(st, x, y, w, h):
    """Screenshot pixels of the spare output -> grim/wf-recorder geometry in global logical coordinates."""
    o = enabled_outputs()[st["output"]]["logical"]
    s = o["scale"]
    return f"{o['x'] + round(x / s)},{o['y'] + round(y / s)} {round(w / s)}x{round(h / s)}"


def grid(st):
    g = st.get("grid")
    if not g:
        raise Refuse("the grid was not measured at start; pixel-to-cell mapping is unavailable")
    w = find_window(st["pid"])
    if w and w["layout"]["window_size"] != st.get("window_size"):
        raise Refuse("the lab window was resized since the grid was measured; restart the lab to remeasure")
    cols, rows = (STATE / "size").read_text().split()[:2]
    if (int(cols), int(rows)) != (g["cols"], g["rows"]):
        raise Refuse(
            f"the terminal is now {cols}x{rows}, not the measured {g['cols']}x{g['rows']}; restart the lab to remeasure"
        )
    return g


# ---------- grid measurement ----------


def read_ppm(path):
    data = Path(path).read_bytes()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
    if m is None:
        raise ValueError(f"{path} is not a binary PPM")
    w, h = int(m.group(1)), int(m.group(2))
    return w, h, data[m.end() :]


def magenta(output):
    """Screenshot the output and find its magenta marker pixels: (x0, y0, x1, y1, count, size), or None."""
    with tempfile.TemporaryDirectory(dir=STATE) as tmp:
        shot = Path(tmp) / "markers.ppm"
        subprocess.run(["grim", "-t", "ppm", "-o", output, str(shot)], check=True)
        w, h, px = read_ppm(shot)
    stride = w * 3
    hit = re.compile(rb"[\xf0-\xff][\x00-\x10][\xf0-\xff]")
    xs, ys, count = [], [], 0
    for y in range(h):
        row = px[y * stride : (y + 1) * stride]
        found = [m.start() // 3 for m in hit.finditer(row) if m.start() % 3 == 0]
        if found:
            xs += [found[0], found[-1]]
            ys.append(y)
            count += len(found)
    if not ys:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1, count, [w, h]


def measure_grid(st):
    """Find the two magenta marker cells the relay paints before the command starts."""
    cols, rows, xpx, _ypx = map(int, (STATE / "size").read_text().split())
    found = magenta(st["output"])
    if not found:
        return None
    x0, y0, x1, y1, count, size = found
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    # Two cell-sized blocks and nothing else, or the wallpaper fooled us.
    if not (0.8 < count / (2 * cw * ch) < 1.2) or (xpx and abs(cw - xpx / cols) > 1):
        return None
    return {
        "x": x0,
        "y": y0,
        "cell_w": round(cw, 3),
        "cell_h": round(ch, 3),
        "cols": cols,
        "rows": rows,
        "screenshot": size,
    }


# ---------- commands ----------


def cmd_preflight(a):
    ok = True

    def item(name, fn):
        nonlocal ok
        try:
            print(f"ok    {name}: {fn()}")
        except Refuse as e:
            ok = False
            print(f"FAIL  {name}: {e}")

    item("niri", check_niri)
    spare = {}

    def output():
        spare["name"], o = spare_output()
        return f"{spare['name']} ({o['logical']['width']}x{o['logical']['height']}, user focused elsewhere)"

    item("spare output", output)
    if "name" in spare:
        item("window rule", lambda: rule_for(spare["name"]))

        def empty():
            ws = next(x for x in niri("workspaces") if x["output"] == spare["name"] and x["is_active"])
            mine = (load_state() or {}).get("pid")
            others = [x["app_id"] for x in niri("windows") if x["workspace_id"] == ws["id"] and x["pid"] != mine]
            if others:
                raise Refuse(
                    f"its active workspace holds {', '.join(map(str, others))}; ask the user to move them off "
                    f"or switch {spare['name']} to an empty workspace"
                )
            return "no other windows on its active workspace"

        item("spare workspace", empty)
    item("app-id", check_app_id)
    item("ghostty", lambda: need("ghostty", "the terminal under test") or shutil.which("ghostty"))
    if a.browser:
        item("chromium", lambda: need("chromium", "the browser under test") or shutil.which("chromium"))
    item("grim", lambda: need("grim", "screenshots without the clipboard") or shutil.which("grim"))
    item("wf-recorder", lambda: need("wf-recorder", "recording GIFs") or shutil.which("wf-recorder"))
    item("ffmpeg", lambda: need("ffmpeg", "GIF conversion") or shutil.which("ffmpeg"))
    item("runtime dir", check_runtime)
    print("ready" if ok else "not ready: fix the FAIL lines (relay the ask-the-user ones), then rerun preflight")
    return 0 if ok else 1


def wait_for_window(pid):
    """The lab's niri window once it appears, or None after about 7s."""
    w = None
    for _ in range(40):
        w = find_window(pid)
        if w:
            break
        time.sleep(0.1 if _ < 20 else 0.25)
    return w


def settle_grid(st):
    """Wait for the relay to report its size, then measure the grid; None if it can't be measured."""
    for _ in range(20):
        if (STATE / "size").exists():
            break
        time.sleep(0.25)
    time.sleep(0.5)
    grid = None
    for _ in range(4):
        grid = measure_grid(st)
        if grid:
            break
        time.sleep(0.5)
    return grid


def claim(output):
    """Refuse unless no lab runs and the spare output's visible workspace is empty. Call it under start_lock."""
    st = load_state()
    if st and alive(st["pid"]):
        check_owner(st)
        raise Refuse(f"a lab is already running (pid {st['pid']}); `lab.py stop` it first")
    ws = next(x for x in niri("workspaces") if x["output"] == output and x["is_active"])
    others = [x["app_id"] for x in niri("windows") if x["workspace_id"] == ws["id"]]
    if others:
        raise Refuse(f"{output}'s active workspace holds {', '.join(map(str, others))}; ask the user to clear it")


def clean_env():
    """Drop this session's CLAUDE* variables so a lab `claude` runs as a fresh session; tmux ones would hide images."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("CLAUDE") and k != "CLAUDE_CONFIG_DIR") and k not in ("TMUX", "TMUX_PANE")
    }


def launch(a, output):
    """Open the lab if the spare output is free, recorded as this session's. Call it under start_lock."""
    claim(output)
    for f in ("go", "size", "osc52.log", "relay.log"):
        (STATE / f).unlink(missing_ok=True)
    if not FEED.is_fifo():
        FEED.unlink(missing_ok=True)
        os.mkfifo(FEED, 0o600)
    env = clean_env()
    log = open(STATE / "ghostty.log", "w")  # noqa: SIM115 -- the detached child keeps writing to it
    proc = subprocess.Popen(
        [
            "ghostty",
            f"--class={APP_ID}",
            *GHOSTTY_FLAGS,
            f"--working-directory={os.path.abspath(a.cwd)}",
            "-e",
            sys.executable,
            str(HERE / "relay.py"),
            str(STATE),
            *a.cmd,
        ],
        env=env,
        cwd=a.cwd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
    st = {"kind": "terminal", "pid": proc.pid, "output": output, "app_id": APP_ID, "cmd": a.cmd, "owner": session()}
    save_state(st)
    return proc, st


def placed(proc, st, output):
    """The new lab window, or close it and refuse unless it is APP_ID on the spare output, unfocused."""
    w = wait_for_window(proc.pid)
    if not w or w["output"] != output or w["app_id"] != APP_ID or w["is_focused"]:
        kill(st)
        where = f"app-id {w['app_id']} on {w['output']}, focused={w['is_focused']}" if w else "no window appeared"
        raise Refuse(
            f"aborted and closed: the lab window must be {APP_ID} on {output}, unfocused ({where}). "
            "If it showed on the user's screen, tell them."
        )
    return w


def cmd_start(a):
    if not a.cmd:
        raise Refuse("usage: lab.py start [--cwd DIR] -- CMD [ARGS...]")
    check_runtime()
    check_niri()
    check_app_id()
    need("ghostty", "the terminal under test")
    need("grim", "screenshots without the clipboard")
    output, _ = spare_output()
    rule_for(output)
    with start_lock():
        proc, st = launch(a, output)
    w = placed(proc, st, output)
    st["grid"] = settle_grid(st)
    st["window_size"] = w["layout"]["window_size"]
    save_state(st)
    (STATE / "go").touch()
    print(
        json.dumps(
            {
                "window": w["id"],
                "pid": proc.pid,
                "output": output,
                "app_id": w["app_id"],
                "focused": w["is_focused"],
                "grid": st["grid"],
            }
        )
    )
    if not st["grid"]:
        print("warning: could not measure the grid; `cell` will be unavailable", file=sys.stderr)
    print("Tell the user: keep the pointer off the spare screen (focus follows mouse).", file=sys.stderr)
    return 0


# ---------- the browser lab ----------

# The profile and downloads live on disk, not in the runtime dir (a tmpfs); `browse` wipes both.
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "niri-screen-lab"


def launch_browser(output):
    """Open Chromium on a fresh profile if the spare output is free, recorded as this session's lab."""
    claim(output)
    shutil.rmtree(CACHE, ignore_errors=True)
    profile = CACHE / "profile"
    browser.prepare_profile(profile, CACHE / "downloads")
    (STATE / "filechooser.log").unlink(missing_ok=True)
    log = open(STATE / "chromium.log", "w")  # noqa: SIM115 -- the detached child keeps writing to it
    proc = subprocess.Popen(
        ["chromium", f"--class={APP_ID}", f"--user-data-dir={profile}", *browser.CHROMIUM_FLAGS, "about:blank"],
        env=clean_env(),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
    st = {
        "kind": "browser",
        "pid": proc.pid,
        "output": output,
        "app_id": APP_ID,
        "cmd": ["chromium"],
        "owner": session(),
        "profile": str(profile),
    }
    save_state(st)
    return proc, st


@contextlib.contextmanager
def page(st):
    """A DevTools connection to the lab's page tab."""
    cdp = browser.CDP(browser.endpoints(st["port"], "page"))
    try:
        yield cdp
    finally:
        cdp.close()


def input_page(st):
    """page(), for commands that act on the page: refused while the lab window has keyboard focus. niri lets
    only the focused client set the clipboard, so an unfocused lab can't write it whatever a page does."""
    w = find_window(st["pid"])
    if w and w["is_focused"]:
        raise Refuse(
            "the lab window has focus (pointer on the spare screen?), so a page could write the clipboard; "
            "ask the user to move the pointer away, then retry"
        )
    return page(st)


def plausible_viewport(found, css_w, css_h):
    x0, y0, x1, y1, count, _ = found
    scale = (x1 - x0) / css_w
    marker_px = browser.MARKER * scale
    # The two marker squares and nothing else, and the same scale both ways, or the wallpaper fooled us.
    return 0.8 < count / (2 * marker_px * marker_px) < 1.2 and abs((y1 - y0) / css_h - scale) < 0.02


def measure_viewport(st):
    """Where the page's viewport sits in a full-output screenshot, found with the marker page; None if not found."""
    with page(st) as cdp:
        browser.navigate(cdp, browser.MARKER_PAGE)
        css_w, css_h = browser.evaluate(cdp, "[innerWidth, innerHeight]")
    for _ in range(5):
        time.sleep(0.3)
        found = magenta(st["output"])
        if found and plausible_viewport(found, css_w, css_h):
            x0, y0, x1, y1, _, size = found
            return {
                "x": x0,
                "y": y0,
                "width": x1 - x0,
                "height": y1 - y0,
                "css_width": css_w,
                "css_height": css_h,
                "screenshot": size,
            }
    return None


def start_keeper(port):
    log = open(STATE / "keeper.log", "w")  # noqa: SIM115 -- the detached keeper keeps writing to it
    p = subprocess.Popen(
        [sys.executable, str(HERE / "browser.py"), "keep", str(STATE), str(port)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
    return p.pid


def cmd_browse(a):
    check_runtime()
    check_niri()
    check_app_id()
    need("chromium", "the browser under test")
    need("grim", "screenshots without the clipboard")
    output, _ = spare_output()
    rule_for(output)
    with start_lock():
        proc, st = launch_browser(output)
    w = placed(proc, st, output)
    try:
        st["port"] = browser.devtools_port(st["profile"])
        st["keeper"] = start_keeper(st["port"])
        st["viewport"] = measure_viewport(st)
        st["window_size"] = w["layout"]["window_size"]
        save_state(st)
        with page(st) as cdp:
            browser.navigate(cdp, a.url)
    except browser.CDPError as e:
        kill(st)
        raise Refuse(f"aborted and closed: {e}")
    print(json.dumps({"window": w["id"], "pid": proc.pid, "output": output, "viewport": st["viewport"]}))
    if not st["viewport"]:
        print("warning: could not find the viewport; `cell`, `--crop` and GIFs are unavailable", file=sys.stderr)
    print("Tell the user: keep the pointer off the spare screen (focus follows mouse).", file=sys.stderr)


def browser_lab(command):
    st = running()
    if kind(st) != "browser":
        raise Refuse(f"`{command}` needs a browser lab; open one with `lab.py browse URL`")
    return st


def cmd_open(a):
    with input_page(browser_lab("open")) as cdp:
        browser.navigate(cdp, a.url)


def cmd_js(a):
    with input_page(browser_lab("js")) as cdp:
        print(json.dumps(browser.evaluate(cdp, a.expression)))


def viewport(st):
    v = st.get("viewport")
    if not v:
        raise Refuse("the viewport was not found at start; pixel mapping and cropping are unavailable")
    w = find_window(st["pid"])
    if w and w["layout"]["window_size"] != st.get("window_size"):
        raise Refuse("the lab window was resized since the viewport was measured; restart the lab to remeasure")
    return v


def feed(data):
    running()
    try:
        fd = os.open(FEED, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        raise Refuse("the relay is not reading its feed; is the lab running?")
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


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


def cmd_keys(a):
    st = running()
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.type_text(cdp, unescape(a.text).decode())
        return
    feed(unescape(a.text))


def cmd_key(a):
    st = running()
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
        feed(key_bytes(name))
        time.sleep(a.delay)


def sgr(button, col, row, final="M"):
    return f"\x1b[<{button};{col};{row}{final}".encode()


def cmd_hover(a):
    st = running()
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.mouse(cdp, "mouseMoved", a.col, a.row)
        return
    feed(sgr(35, a.col, a.row))


BUTTONS = {"left": 0, "middle": 1, "right": 2}


def cmd_click(a):
    st = running()
    if kind(st) == "browser":
        with input_page(st) as cdp:
            browser.mouse(cdp, "mouseMoved", a.col, a.row)
            browser.mouse(cdp, "mousePressed", a.col, a.row, a.button, 1)
            browser.mouse(cdp, "mouseReleased", a.col, a.row, a.button, 1)
        return
    b = BUTTONS[a.button]
    feed(sgr(35, a.col, a.row))
    time.sleep(0.05)
    feed(sgr(b, a.col, a.row))
    time.sleep(0.05)
    feed(sgr(b, a.col, a.row, "m"))


def cmd_scroll(a):
    st = running()
    if kind(st) == "browser":
        with input_page(st) as cdp:
            dy = (-100 if a.direction == "up" else 100) * a.count
            browser.mouse(cdp, "mouseWheel", a.col, a.row, deltaX=0, deltaY=dy)
        return
    for _ in range(a.count):
        feed(sgr(64 if a.direction == "up" else 65, a.col, a.row))
        time.sleep(0.03)


def page_info(st):
    if kind(st) != "browser":
        return None
    with page(st) as cdp:
        return browser.evaluate(cdp, "({url: location.href, title: document.title})")


def cmd_info(a):
    st = running()
    w = find_window(st["pid"])
    size = (STATE / "size").read_text().split() if (STATE / "size").exists() else []
    print(
        json.dumps(
            {
                "pid": st["pid"],
                "output": st["output"],
                "cmd": st["cmd"],
                "window": w and {k: w[k] for k in ("id", "app_id", "is_focused", "workspace_id", "output")},
                "size": size and dict(zip(("cols", "rows", "xpixel", "ypixel"), map(int, size))),
                "kind": kind(st),
                "grid": st.get("grid"),
                "viewport": st.get("viewport"),
                "page": page_info(st),
                "recording": bool(st.get("rec")),
            },
            indent=1,
        )
    )


def css_point(v, x, y, crop):
    """A pixel in a full or --crop screenshot -> the page's CSS pixel, which hover, click and scroll take."""
    if not crop:
        x, y = x - v["x"], y - v["y"]
    if not (0 <= x < v["width"] and 0 <= y < v["height"]):
        return None
    return round(x * v["css_width"] / v["width"]), round(y * v["css_height"] / v["height"])


def cmd_cell(a):
    st = running()
    if kind(st) == "browser":
        point = css_point(viewport(st), a.x, a.y, a.crop)
        if point is None:
            raise Refuse(f"pixel ({a.x},{a.y}) is outside the page's viewport")
        print(*point)
        return
    g = grid(st)
    x, y = (a.x, a.y) if a.crop else (a.x - g["x"], a.y - g["y"])
    col, row = int(x // g["cell_w"]) + 1, int(y // g["cell_h"]) + 1
    if not (1 <= col <= g["cols"] and 1 <= row <= g["rows"]):
        raise Refuse(f"pixel ({a.x},{a.y}) is outside the terminal grid")
    print(col, row)


def grid_rect(st):
    if kind(st) == "browser":
        v = viewport(st)
        return global_rect(st, v["x"], v["y"], v["width"], v["height"])
    g = grid(st)
    return global_rect(st, g["x"], g["y"], g["cols"] * g["cell_w"], g["rows"] * g["cell_h"])


def cmd_shot(a):
    need("grim", "screenshots without the clipboard")
    st = running()
    alone(st)
    out = os.path.abspath(a.file)
    args = ["-g", grid_rect(st)] if a.crop else ["-o", st["output"]]
    subprocess.run(["grim", *args, out], check=True)
    print(out)


def rec_start(st, crop):
    need("wf-recorder", "recording GIFs")
    need("ffmpeg", "GIF conversion")
    if st.get("rec") and alive_pid(st["rec"]["pid"]):
        raise Refuse("already recording; `lab.py rec-stop FILE.gif` first")
    alone(st)
    video = str(STATE / "rec.mp4")
    args = ["-g", grid_rect(st)] if crop else ["-o", st["output"]]
    log = open(STATE / "rec.log", "w")  # noqa: SIM115 -- the detached recorder keeps writing to it
    p = subprocess.Popen(
        ["wf-recorder", "-y", *args, "-f", video],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    st["rec"] = {"pid": p.pid, "video": video}
    save_state(st)
    time.sleep(0.6)
    if p.poll() is not None:
        st.pop("rec")
        save_state(st)
        raise Refuse(f"wf-recorder exited: {(STATE / 'rec.log').read_text()[-400:]}")


def alive_pid(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def rec_stop(st, out, fps, width):
    rec = st.pop("rec", None)
    save_state(st)
    if not rec:
        raise Refuse("not recording")
    os.kill(rec["pid"], signal.SIGINT)
    for _ in range(50):
        if not alive_pid(rec["pid"]):
            break
        time.sleep(0.1)
    try:
        alone(st)
    except Refuse as e:
        os.unlink(rec["video"])
        raise Refuse(f"discarded the recording: {e}")
    vf = (
        f"fps={fps},scale='min({width},iw)':-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5"
    )
    out = os.path.abspath(out)
    ff = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", rec["video"], "-vf", vf, "-loop", "0", out],
        capture_output=True,
        text=True,
        check=False,
    )
    os.unlink(rec["video"])
    if ff.returncode != 0:
        # wf-recorder records frames only when the screen changes, so a recording of a still screen holds one.
        last = (ff.stderr.strip().splitlines() or ["no output"])[-1]
        raise Refuse(
            f"ffmpeg could not make the GIF ({last}); if nothing on the lab screen moved while recording, "
            "take a `shot` instead"
        )
    print(out, f"{os.path.getsize(out) // 1024} KiB")


def cmd_gif(a):
    st = running()
    rec_start(st, a.crop)
    time.sleep(a.seconds)
    rec_stop(load_state(), a.file, a.fps, a.width)


def cmd_rec_start(a):
    rec_start(running(), a.crop)
    print("recording; run `lab.py rec-stop FILE.gif` to finish")


def cmd_rec_stop(a):
    rec_stop(running(), a.file, a.fps, a.width)


def kill(st):
    rec = st.get("rec")
    if rec and alive_pid(rec["pid"]):
        os.kill(rec["pid"], signal.SIGINT)
    # End the process itself: closing Ghostty's window through niri leaves a "close running process?" dialog.
    if alive(st["pid"]):
        os.kill(st["pid"], signal.SIGTERM)
    for i in range(40):
        if not find_window(st["pid"]) and not alive(st["pid"]):
            break
        if i == 20 and alive(st["pid"]):
            os.kill(st["pid"], signal.SIGKILL)
        time.sleep(0.25)
    if st.get("keeper") and alive_pid(st["keeper"]):
        os.kill(st["keeper"], signal.SIGTERM)
    if st.get("profile"):
        shutil.rmtree(st["profile"], ignore_errors=True)
    STATE_FILE.unlink(missing_ok=True)
    for f in ("go", "size", "rec.mp4"):
        (STATE / f).unlink(missing_ok=True)
    if find_window(st["pid"]):
        raise Refuse("the lab window is still open; tell the user")


def cmd_stop(a):
    st = load_state()
    if not st:
        print("no lab running")
        return
    kill(st)
    print("stopped")


# Commands that never touch a running lab. Every other one is refused while another session owns the lab.
LAB_FREE = {"preflight", "doctor"}


def parser():
    p = argparse.ArgumentParser(prog="lab.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("preflight", aliases=["doctor"], help="check every prerequisite")
    s.add_argument("--browser", action="store_true", help="also check what `browse` needs")
    s.set_defaults(fn=cmd_preflight)
    s = sub.add_parser("start", help="open the lab window running CMD")
    s.add_argument("--cwd", default=os.getcwd())
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("keys", help="feed raw bytes (printf escapes: \\e \\r \\x15 ...)")
    s.add_argument("text")
    s.set_defaults(fn=cmd_keys)
    s = sub.add_parser("key", help="named keys: enter esc tab up ctrl-u alt-x ...")
    s.add_argument("names", nargs="+")
    s.add_argument("--delay", type=float, default=0.05)
    s.set_defaults(fn=cmd_key)
    s = sub.add_parser("browse", help="open the browser lab (Chromium) at URL")
    s.add_argument("url", nargs="?", default="about:blank")
    s.set_defaults(fn=cmd_browse)
    s = sub.add_parser("open", help="browser lab: go to URL")
    s.add_argument("url")
    s.set_defaults(fn=cmd_open)
    s = sub.add_parser("js", help="browser lab: evaluate a JavaScript expression in the page, print its JSON")
    s.add_argument("expression")
    s.set_defaults(fn=cmd_js)
    for name, fn in (("hover", cmd_hover), ("click", cmd_click)):
        s = sub.add_parser(name, help=f"mouse {name} at a 1-based cell (terminal) or a CSS pixel (browser)")
        s.add_argument("col", type=int, metavar="COL|X")
        s.add_argument("row", type=int, metavar="ROW|Y")
        if name == "click":
            s.add_argument("--button", choices=BUTTONS, default="left")
        s.set_defaults(fn=fn)
    s = sub.add_parser("scroll", help="mouse wheel at a cell (terminal) or a CSS pixel (browser)")
    s.add_argument("direction", choices=("up", "down"))
    s.add_argument("col", type=int, metavar="COL|X")
    s.add_argument("row", type=int, metavar="ROW|Y")
    s.add_argument("--count", type=int, default=1)
    s.set_defaults(fn=cmd_scroll)
    sub.add_parser("info", help="window, size and grid as JSON").set_defaults(fn=cmd_info)
    s = sub.add_parser("cell", help="screenshot pixel -> col row (terminal) or page x y (browser)")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s.add_argument("--crop", action="store_true", help="pixel is from a --crop screenshot")
    s.set_defaults(fn=cmd_cell)
    s = sub.add_parser("shot", help="PNG of the spare output (or --crop: the terminal grid or page viewport)")
    s.add_argument("file")
    s.add_argument("--crop", action="store_true")
    s.set_defaults(fn=cmd_shot)
    for name, fn in (("gif", cmd_gif), ("rec-start", cmd_rec_start), ("rec-stop", cmd_rec_stop)):
        s = sub.add_parser(
            name,
            help={
                "gif": "record SECONDS then write FILE.gif",
                "rec-start": "start recording",
                "rec-stop": "stop recording and write FILE.gif",
            }[name],
        )
        if name != "rec-start":
            s.add_argument("file")
        if name == "gif":
            s.add_argument("seconds", type=float)
        if name != "rec-stop":
            s.add_argument("--crop", action="store_true")
        if name != "rec-start":
            s.add_argument("--fps", type=int, default=12)
            s.add_argument("--width", type=int, default=1200)
        s.set_defaults(fn=fn)
    sub.add_parser("stop", help="close the lab (Ghostty or Chromium) and clean up").set_defaults(fn=cmd_stop)
    return p


def main():
    a = parser().parse_args()
    if getattr(a, "cmd", None) and a.cmd[0] == "--":
        a.cmd = a.cmd[1:]
    try:
        if a.command not in LAB_FREE and (st := load_state()):
            check_owner(st)
        sys.exit(a.fn(a) or 0)
    except (Refuse, browser.CDPError) as e:
        print(f"niri-screen-lab: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
