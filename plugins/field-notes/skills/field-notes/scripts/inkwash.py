#!/usr/bin/env python3
"""Build Field Notes illustrations: body file -> sketch JSON -> SVG -> PNG preview.

    inkwash.py setup                         install the renderer's Node packages (once)
    inkwash.py build BODY.py [--out DIR]     sketch, render and preview one drawing
    inkwash.py preview OUT.png A.svg [B.svg ...]
    inkwash.py crop DRAWING.svg OUT.png X Y W H

A body file draws with the marks it imports from kit.py, which sits next to this script. The Node
packages (perfect-freehand for the strokes, Playwright for the previews) go to a cache folder outside
the skill, so a plugin update never loses them and they are installed only once.
"""

import argparse
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import kit

HERE = Path(__file__).resolve().parent
PACKAGE_FILES = ("package.json", "package-lock.json")


def node_dir() -> Path:
    """Where the renderer's Node packages live: $FIELD_NOTES_NODE_DIR, else the user's cache folder."""
    if os.environ.get("FIELD_NOTES_NODE_DIR"):
        return Path(os.environ["FIELD_NOTES_NODE_DIR"])
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "field-notes" / "node"


def installed(target: Path) -> bool:
    """True when the packages in target were installed from this skill's package files."""
    if not (target / "node_modules").is_dir():
        return False
    return all(
        (target / name).is_file() and (target / name).read_bytes() == (HERE / name).read_bytes()
        for name in PACKAGE_FILES
    )


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"inkwash: {tool} is not on PATH; install Node.js 20 or newer")
    return path


def setup(browser: bool = True) -> Path:
    """Install the Node packages (and Playwright's Chromium) unless they are already current."""
    target = node_dir()
    if not installed(target):
        target.mkdir(parents=True, exist_ok=True)
        for name in PACKAGE_FILES:
            shutil.copyfile(HERE / name, target / name)
        print(f"inkwash: installing the renderer's Node packages into {target}", file=sys.stderr)
        subprocess.run([need("npm"), "ci", "--no-audit", "--no-fund"], cwd=target, check=True)
    if browser:
        cli = target / "node_modules" / "playwright" / "cli.js"
        subprocess.run([need("node"), str(cli), "install", "chromium"], cwd=target, check=True)
    return target


def node(script: str, *args: str) -> None:
    """Run one of the skill's Node scripts with the cached packages on its module path."""
    target = node_dir() if installed(node_dir()) else setup(browser=False)
    env = dict(os.environ)
    env["NODE_PATH"] = os.pathsep.join(p for p in (str(target / "node_modules"), env.get("NODE_PATH")) if p)
    subprocess.run([need("node"), str(HERE / script), *args], env=env, check=True)


def sketch(body: Path, out: Path, seed: int, stroke: float) -> int:
    """Run a body file against a fresh kit and save its sketch. Returns the element count."""
    kit.reset(seed=seed, stroke=stroke, group=f"icon-{body.stem}")
    names = runpy.run_path(str(body), run_name="__field_notes__")
    name = names.get("NAME") or body.stem.replace("_", " ").replace("-", " ").capitalize()
    return kit.save(f"lib-{body.stem}", name, str(out))


def build(args: argparse.Namespace) -> None:
    body = Path(args.body)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = body.stem
    json_path, svg, png = out / f"{stem}.sketch.json", out / f"{stem}.svg", out / f"{stem}.png"
    count = sketch(body, json_path, args.seed, args.stroke)
    print(f"{json_path}: {count} elements")
    render = [str(json_path), str(svg), "--px", str(args.px)] + (["--paper"] if args.paper else [])
    node("render.js", *render)
    if args.preview:
        node("prev.js", str(png), *args.compare, str(svg))
        print(png)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inkwash.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="install the renderer's Node packages and Playwright's Chromium")
    s.add_argument("--no-browser", dest="browser", action="store_false", help="skip the Chromium download")
    b = sub.add_parser("build", help="body file -> sketch JSON -> SVG -> PNG preview")
    b.add_argument("body", help="a body file that draws with kit.py")
    b.add_argument("--out", default=".", help="output folder (default: the current folder)")
    b.add_argument("--seed", type=int, default=7, help="the hand's random seed (default 7)")
    b.add_argument("--stroke", type=float, default=0.1, help="base stroke width (default 0.1)")
    b.add_argument("--px", type=int, default=1400, help="SVG width in pixels (default 1400)")
    b.add_argument("--paper", action="store_true", help="render on a paper background (leave off for icons)")
    b.add_argument("--no-preview", dest="preview", action="store_false", help="skip the PNG preview")
    b.add_argument("--compare", action="append", default=[], metavar="SVG", help="show this SVG left of the drawing")
    v = sub.add_parser("preview", help="render SVGs side by side to a PNG")
    v.add_argument("png")
    v.add_argument("svgs", nargs="+")
    c = sub.add_parser("crop", help="zoom into world coordinates X Y W H of an SVG (see its viewBox)")
    c.add_argument("svg")
    c.add_argument("png")
    c.add_argument("box", nargs=4, metavar=("X", "Y", "W", "H"))
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "setup":
        print(setup(browser=args.browser))
    elif args.command == "build":
        build(args)
    elif args.command == "preview":
        node("prev.js", args.png, *args.svgs)
    else:
        node("crop.js", args.svg, args.png, *args.box)


if __name__ == "__main__":
    main()
