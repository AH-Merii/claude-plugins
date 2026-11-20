"""A photo drawn from its paint-then-trace output: ink from the painting's line work, washes from its colour regions.

Point TRACE at the trace.json that scripts/paint_trace.py wrote (default: ./trace.json), then build this file.
Copy it into your working folder to tune it; the numbers here gave the approved portrait.
"""

import json
import os
from pathlib import Path

from kit import _stroke, blob, dot

NAME = "Traced photo"
T = json.loads(Path(os.environ.get("TRACE", "trace.json")).read_text())

# invisible corner dots fix the drawing's extent to the photo's frame
for x, y in ((0, 0), (T["w"], 0), (0, T["h"]), (T["w"], T["h"])):
    dot(x, y, 0.05, op=0)

# ink: long lines first, then the details; thicker and darker lines press harder
for s in T["ink"]:
    w = 0.2 + 0.18 * min(s["thick"], 2.5) + 0.14 * min(1.0, s["len"] / 20)
    _stroke([tuple(p) for p in s["pts"]], w=w, op=int(70 + 30 * min(1.0, s["dark"] * 1.4)), taper=False)


def soften(rgb, k):
    return "#" + "".join(f"{int(c + (255 - c) * k):02x}" for c in rgb)


# washes, light to dark; the lightest regions stay paper
for r in T["washes"]:
    if r["lum"] > 0.92:
        continue
    pts = [tuple(p) for p in r["pts"]]
    dark = r["lum"] < 0.3
    grey = max(r["rgb"]) - min(r["rgb"]) < 40  # greys stay light so the paper shows, as in the relay array
    k = 0.6 if grey and not dark else 1.0
    colour = soften(r["rgb"], 0.0 if dark else 0.1)
    blob(pts, colour, (40 if dark else 46) * k, wob=0.3)
    blob(pts, colour, 26 * k, wob=0.22, grow=-0.25)
