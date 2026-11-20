#!/usr/bin/env python3
"""Put the check images of items finished since the last sheet on one contact sheet; print its path.

    contact_sheet.py --image 'out/{prefix}-hand-drawn/check/{key}.png' [--cols 2] [--width 900]

Run it from the run folder (or pass --dir). It reads logs/costs.tsv (one line per finished fork,
redos included), leaves out approved items and items already shown (logs/shown.txt), and writes
sheets/batch-NN.html and sheets/batch-NN.png, each image labelled with its key. `{key}` in --image is
the item key and `{prefix}` its part before the first "-". The PNG is rendered with the field-notes
skill's Chromium.
"""

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "field-notes" / "scripts"))

import inkwash  # the field-notes skill's build script: its Node packages and Chromium

REDO = re.compile(r"-redo\d+$")


def lines(path: Path) -> list[str]:
    return path.read_text().split() if path.exists() else []


def new_items(run: Path, image: str) -> list[tuple[str, str, Path]]:
    """(tag, key, image) for each finished fork not shown yet whose item isn't approved; latest per key."""
    costs = run / "logs" / "costs.tsv"
    tags = [line.split("\t")[0] for line in costs.read_text().splitlines() if line.strip()] if costs.exists() else []
    shown = set(lines(run / "logs" / "shown.txt"))
    approved = set(lines(run / "approved.txt"))
    latest: dict[str, tuple[str, str, Path]] = {}
    for tag in tags:
        key = REDO.sub("", tag)
        path = run / image.format(key=key, prefix=key.split("-")[0])
        if tag in shown or key in approved or not path.exists():
            continue
        latest.pop(key, None)
        latest[key] = (tag, key, path)
    return list(latest.values())


def page(items: list[tuple[str, str, Path]], cols: int, width: int) -> str:
    cards = "".join(
        f'<figure style="margin:0;background:#fff;padding:8px">'
        f'<figcaption style="font:14px sans-serif;margin-bottom:6px">{html.escape(tag)}</figcaption>'
        f'<img src="{path.resolve().as_uri()}" style="width:{width}px;display:block"></figure>'
        for tag, _, path in items
    )
    return (
        '<html><body style="margin:0;background:#ddd">'
        f'<div id="sheet" style="display:inline-grid;grid-template-columns:repeat({cols},auto);gap:12px;'
        f'padding:12px">{cards}</div></body></html>'
    )


def render(html_path: Path, png: Path) -> None:
    target = inkwash.node_dir() if inkwash.installed(inkwash.node_dir()) else inkwash.setup()
    env = dict(os.environ, NODE_PATH=str(target / "node_modules"))
    subprocess.run([inkwash.need("node"), str(HERE / "sheet.js"), str(png), str(html_path)], env=env, check=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", required=True, help="check image path relative to the run folder, with {key}/{prefix}")
    p.add_argument("--dir", default=os.environ.get("BATCH_DIR", "."), help="the run folder (default: $BATCH_DIR or .)")
    p.add_argument("--cols", type=int, default=2)
    p.add_argument("--width", type=int, default=900, help="width of each image in CSS px")
    args = p.parse_args(argv)
    run = Path(args.dir).resolve()
    items = new_items(run, args.image)
    if not items:
        sys.exit("nothing new")
    sheets = run / "sheets"
    sheets.mkdir(exist_ok=True)
    taken = [int(m.group(1)) for f in os.listdir(sheets) if (m := re.match(r"batch-(\d+)\.", f))]
    stem = sheets / f"batch-{max(taken, default=0) + 1:02d}"
    html_path, png = stem.with_suffix(".html"), stem.with_suffix(".png")
    html_path.write_text(page(items, args.cols, args.width))
    render(html_path, png)
    with open(run / "logs" / "shown.txt", "a") as f:
        f.writelines(tag + "\n" for tag, _, _ in items)
    print(png, len(items))
    for _, key, _ in items:
        print(f"  {key}")


if __name__ == "__main__":
    main()
