"""inkwash drawing kit: the marks that make a Field Notes illustration.

A body file imports what it needs from here and draws. inkwash.py resets the kit, runs the body
and saves the sketch, which render.js turns into an ink-and-watercolour SVG.

The sketch is a list of Excalidraw elements:
- ink: freedraw strokes with pressure, overshooting corners, restated, slightly bowed;
- wash: translucent irregular polygons layered and offset from the ink, pooling darker at one side,
  with white paper left showing;
- character: splatter dots, dark accents, a loose ground shadow.

Coordinates are world units, y down. Light comes from the upper left.
"""

import contextlib
import itertools
import json
import math
import random
from collections.abc import Generator
from typing import Any

Point = tuple[float, float]

rnd = random.Random(7)
SW = 0.1  # base stroke width; every pen mark scales from it
G = ["field-notes"]
els: list[dict[str, Any]] = []
OVER = [False]  # True while drawing forms that stand in front of earlier ink (rendered in their own top layer)
INK = "#1e1e1e"


def reset(seed: int = 7, stroke: float = 0.1, group: str = "field-notes") -> None:
    """Start a new drawing: reseed the hand, set the base stroke width and empty the sketch."""
    global SW, LIGHT_AWAY, LW
    rnd.seed(seed)
    SW = stroke
    G[:] = [group]
    els.clear()
    OVER[0] = False
    LIGHT_AWAY, LW = (0.6, 0.8), 0.5


def base(t):
    return {
        "id": f"fn{rnd.randrange(10**7):07d}",
        "type": t,
        "angle": 0,
        "strokeStyle": "solid",
        "opacity": 100,
        "groupIds": G,
        "frameId": None,
        "seed": rnd.randrange(2**31),
        "version": 1,
        "versionNonce": rnd.randrange(2**31),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "roundness": None,
        "fillStyle": "solid",
        "roughness": 0,
        "strokeWidth": 1,
        "backgroundColor": "transparent",
        "strokeColor": INK,
        **({"customData": {"over": True}} if OVER[0] else {}),
    }


def place(e, pts):
    x0, y0 = pts[0]
    e["x"], e["y"] = round(x0, 2), round(y0, 2)
    e["points"] = [[round(x - x0, 2), round(y - y0, 2)] for x, y in pts]
    xs = [p[0] for p in e["points"]]
    ys = [p[1] for p in e["points"]]
    e["width"] = round(max(xs) - min(xs), 2)
    e["height"] = round(max(ys) - min(ys), 2)
    return e


def ink(p, q, w=1.0, over=(1.5, 4.5), bow=1.0, restate=0.7, colour=INK, op=100):
    """One pen stroke p->q that overshoots both ends; sometimes restated with a second pass."""
    passes = 1 + (rnd.random() < restate) + (rnd.random() < restate * 0.4)
    for k in range(passes):
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        o1, o2 = rnd.uniform(*over), rnd.uniform(*over)
        off = rnd.uniform(-0.7, 0.7) if k else rnd.uniform(-0.2, 0.2)
        b = rnd.uniform(-bow, bow)
        n = max(8, int(L / 1.0))
        ph = rnd.uniform(4, 11)
        pts, pr = [], []
        for i in range(n + 1):
            t = i / n
            s = -o1 + (L + o1 + o2) * t
            wob = b * math.sin(math.pi * t) + 0.35 * math.sin(t * ph) + rnd.uniform(-0.15, 0.15)
            pts.append((p[0] + ux * s + nx * (off + wob), p[1] + uy * s + ny * (off + wob)))
            pr.append(
                max(0.15, min(1, (0.35 + 0.65 * math.sin(math.pi * min(1, t * 1.15))) * w * rnd.uniform(0.85, 1.1)))
            )
        e = base("freedraw")
        e["strokeColor"] = colour
        e["strokeWidth"] = SW * (0.75 if k else 1)
        e["opacity"] = op if not k else int(op * 0.8)
        e["pressures"] = [round(v, 2) for v in pr]
        e["simulatePressure"] = False
        e["lastCommittedPoint"] = None
        els.append(place(e, pts))


def poly(pts, closed=True, **kw):
    seq = pts + ([pts[0]] if closed else [])
    for a, b in itertools.pairwise(seq):
        ink(a, b, **kw)


def loop(cx, cy, rx, ry, w=0.9, colour=INK, turns=1.12, op=100):
    """Ellipse drawn in one go: starts and ends past each other, a little off-round."""
    n = 40
    a0 = rnd.uniform(0, 2 * math.pi)
    pts, pr = [], []
    jx, jy = rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3)
    for i in range(n + 1):
        t = i / n
        a = a0 + 2 * math.pi * turns * t
        r = 1 + 0.04 * math.sin(3 * a + a0) + 0.02 * t
        pts.append((cx + jx * t + rx * r * math.cos(a), cy + jy * t + ry * r * math.sin(a)))
        pr.append(max(0.2, min(1, (0.4 + 0.6 * math.sin(math.pi * t)) * w)))
    e = base("freedraw")
    e["strokeColor"] = colour
    e["strokeWidth"] = SW
    e["opacity"] = op
    e["pressures"] = [round(v, 2) for v in pr]
    e["simulatePressure"] = False
    e["lastCommittedPoint"] = None
    els.append(place(e, pts))


def blob(pts, colour, op, wob=0.9, grow=0.0):
    """Wash: irregular translucent shape, soft (curved) wobbly edge."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    dense = []
    seq = pts + [pts[0]]
    for a, b in itertools.pairwise(seq):
        for i in range(3):
            t = i / 3
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            x += (x - cx) * grow + rnd.uniform(-wob, wob)
            y += (y - cy) * grow + rnd.uniform(-wob, wob)
            dense.append((x, y))
    dense.append(dense[0])
    e = base("line")
    e["strokeColor"] = "transparent"
    e["backgroundColor"] = colour
    e["opacity"] = op
    e["roundness"] = {"type": 2}
    e["polygon"] = True
    e["startBinding"] = e["endBinding"] = None
    e["startArrowhead"] = e["endArrowhead"] = None
    e["lastCommittedPoint"] = None
    els.append(place(e, dense))


def wash(pts, colour, op=30, layers=2, pool=None):
    for k in range(layers):
        blob(pts, colour, op, grow=rnd.uniform(-0.08, 0.04))
    if pool:  # pigment pools at one end: smaller darker blob
        blob(pool, colour, min(80, op + 20), wob=0.5)


def dot(x, y, r, colour=INK, op=100):
    e = base("ellipse")
    e["strokeColor"] = "transparent"
    e["backgroundColor"] = colour
    e["opacity"] = op
    e["x"], e["y"], e["width"], e["height"] = x - r, y - r * rnd.uniform(0.7, 1.0), 2 * r, 2 * r * rnd.uniform(0.7, 1.0)
    e["angle"] = rnd.uniform(0, 3)
    els.append(e)


def ink_path(path, w=1.0, over=(0.4, 1.5), restate=0.5, colour=INK, op=100, jit=0.18):
    """Pen stroke along a polyline path (already rounded), overshooting a little along its end tangents."""
    passes = 1 + (rnd.random() < restate)
    for k in range(passes):
        (ax, ay), (bx, by) = path[0], path[1]
        L = math.hypot(bx - ax, by - ay) or 1
        (cx, cy), (dx_, dy_) = path[-2], path[-1]
        M = math.hypot(dx_ - cx, dy_ - cy) or 1
        o1, o2 = rnd.uniform(*over), rnd.uniform(*over)
        P = (
            [(ax - (bx - ax) / L * o1, ay - (by - ay) / L * o1)]
            + path
            + [(dx_ + (dx_ - cx) / M * o2, dy_ + (dy_ - cy) / M * o2)]
        )
        # resample densely
        R = []
        for a, b in itertools.pairwise(P):
            n = max(1, int(math.dist(a, b) / 0.8))
            for i in range(n):
                t = i / n
                R.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        R.append(P[-1])
        off = rnd.uniform(-0.5, 0.5) if k else 0
        ph = rnd.uniform(0, 6)
        fr = rnd.uniform(0.15, 0.35)
        pts, pr = [], []
        N = len(R)
        for i, (x, y) in enumerate(R):
            a, b = R[max(0, i - 1)], R[min(N - 1, i + 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            l = math.hypot(tx, ty) or 1
            nx, ny = -ty / l, tx / l
            wv = off + 0.3 * math.sin(i * fr + ph) + rnd.uniform(-jit, jit) * 0.5
            pts.append((x + nx * wv, y + ny * wv))
            t = i / (N - 1)
            pr.append(
                max(0.15, min(1, (0.35 + 0.65 * math.sin(math.pi * min(1, t * 1.1))) * w * rnd.uniform(0.85, 1.1)))
            )
        e = base("freedraw")
        e["strokeColor"] = colour
        e["strokeWidth"] = SW * (0.75 if k else 1)
        e["opacity"] = op if not k else int(op * 0.8)
        e["pressures"] = [round(v, 2) for v in pr]
        e["simulatePressure"] = False
        e["lastCommittedPoint"] = None
        els.append(place(e, pts))


def fillet(a, b, c, r, n=6):
    """Points of a rounded corner at b between edges a-b and b-c (quadratic curve)."""
    la, lc = math.dist(a, b), math.dist(b, c)
    rr = min(r, la * 0.45, lc * 0.45)
    p0 = (b[0] + (a[0] - b[0]) / la * rr, b[1] + (a[1] - b[1]) / la * rr)
    p2 = (b[0] + (c[0] - b[0]) / lc * rr, b[1] + (c[1] - b[1]) / lc * rr)
    return [
        (
            (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * b[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * b[1] + t * t * p2[1],
        )
        for t in [i / n for i in range(n + 1)]
    ]


def rpoly(pts, r=3.5, closed=False, **kw):
    """Contour with rounded corners, drawn as overlapping strokes: each stroke runs from the middle of
    one corner's curve, along an edge, through the next corner's curve, so corners are curves, never joints."""
    P = pts + ([pts[0], pts[1]] if closed else [])
    corners = {i: fillet(P[i - 1], P[i], P[i + 1], r) for i in range(1, len(P) - 1)}
    segs = range(len(P) - 1) if not closed else range(1, len(P) - 1)
    for i in segs:
        path = []
        if i in corners:
            path += corners[i][len(corners[i]) // 2 :]
        else:
            path.append(P[i])
        if i + 1 in corners:
            path += corners[i + 1][: len(corners[i + 1]) // 2 + 2]
        else:
            path.append(P[i + 1])
        ink_path(path, **kw)


def soft(p, q, w=0.45, op=75):
    """Inner edge of a rounded form: thin, broken, lighter, since a round edge has no crisp line."""
    t1 = rnd.uniform(0.35, 0.5)
    t2 = t1 + rnd.uniform(0.08, 0.15)
    m1 = (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)
    m2 = (p[0] + (q[0] - p[0]) * t2, p[1] + (q[1] - p[1]) * t2)
    ink(p, m1, w=w, over=(0, 0.8), restate=0.2, op=op, bow=0.3)
    ink(m2, q, w=w, over=(0, 0.8), restate=0.2, op=op, bow=0.3)


def granulate(pts, colour, n=25, op=45):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    for _ in range(n):
        dot(rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys)), rnd.uniform(0.12, 0.3), colour, op)


# ---------- precise marks: where a real sketcher slows down and rules it ----------
# Loose ink is for big silhouettes and soft edges. Small, repeated or mechanical parts (buttons, lamps,
# screws, louvres, coils, anything that must line up on an axis) are drawn exact: true ellipses,
# straight even lines, colour filled cleanly inside the line (no bleed past the edge).
HAND = 1.0  # 0 = ruled; 1 = careful hand: the mark is exactly where it belongs, but the line itself is drawn

LIGHT_AWAY = (0.6, 0.8)  # unit vector pointing away from the light (light is upper left)
LW = 0.5  # how strongly line weight follows light: shadow-side edges heavier, lit edges lighter


def shade_mult(nx, ny):
    return 1 + LW * (nx * LIGHT_AWAY[0] + ny * LIGHT_AWAY[1])


def _stroke(pts, w=0.6, colour=INK, op=100, taper=True, mult=None):
    """A careful pen line: position stays exact, but the stroke breathes: a slow sway of a few hundredths,
    weight that swells and lifts, and ends that taper like a nib leaving the paper."""
    N = len(pts)
    pr = []
    L = sum(math.dist(a, b) for a, b in itertools.pairwise(pts)) or 1
    ph, fr = rnd.uniform(0, 6.3), rnd.uniform(1.2, 2.2)  # sway: slow, about one wave per stroke
    amp = HAND * min(0.09, 0.012 * L + 0.02)
    ph2 = rnd.uniform(0, 6.3)
    swell = HAND * rnd.uniform(0.12, 0.28)
    w = w * (rnd.uniform(0.85, 1.18) if taper else 1)
    out = []
    s = 0.0
    for i in range(N):
        if i:
            s += math.dist(pts[i - 1], pts[i])
        t = min(1.0, max(0.0, s / L))
        a, b = pts[max(0, i - 1)], pts[min(N - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        n = math.hypot(tx, ty) or 1
        off = amp * math.sin(fr * math.pi * t + ph) * math.sin(math.pi * t)
        out.append((pts[i][0] - ty / n * off, pts[i][1] + tx / n * off))
        f = (0.5 + 0.5 * max(0.0, math.sin(math.pi * t)) ** 0.6) if taper else 1.0
        f *= 1 + swell * math.sin(2.3 * math.pi * t + ph2)
        if mult:
            f *= mult[i]
        pr.append(round(max(0.15, min(1, w * f)), 2))
    e = base("freedraw")
    e["strokeColor"] = colour
    e["strokeWidth"] = SW
    e["opacity"] = op
    e["pressures"] = pr
    e["simulatePressure"] = False
    e["lastCommittedPoint"] = None
    e["customData"] = {**e.get("customData", {}), "precise": True, **({} if taper else {"flat": True})}
    els.append(place(e, out))


def pline(p, q, w=0.6, colour=INK, op=100, normal=None):
    if normal:
        w = w * shade_mult(*normal)
    L = math.dist(p, q) or 1
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    o1 = HAND * rnd.uniform(0, 0.12) * min(1, L / 2)
    o2 = HAND * rnd.uniform(0.04, 0.22) * min(1, L / 2)
    p = (p[0] - ux * o1, p[1] - uy * o1)
    q = (q[0] + ux * o2, q[1] + uy * o2)
    n = max(6, int(math.dist(p, q) / 0.6))
    _stroke([(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n) for i in range(n + 1)], w, colour, op)


def parc(cx, cy, rx, ry, a0, a1, w=0.5, colour=INK, op=100, n=36):
    angs = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    pts = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in angs]
    mult = []
    for a in angs:  # outward normal of the ellipse at this point
        nx, ny = math.cos(a) / max(rx, 1e-3), math.sin(a) / max(ry, 1e-3)
        l = math.hypot(nx, ny) or 1
        mult.append(shade_mult(nx / l, ny / l))
    _stroke(pts, w, colour, op, mult=mult)


def pell(cx, cy, rx, ry, w=0.5, colour=INK, op=100, n=72):
    # a closed ellipse that meets itself exactly: two half-strokes so the taper never leaves a gap
    a0 = rnd.uniform(0, 2 * math.pi)
    ov = 0.12 + HAND * rnd.uniform(0, 0.12)
    parc(cx, cy, rx, ry, a0 - ov, a0 + math.pi + ov, w, colour, op, n // 2)
    parc(cx, cy, rx, ry, a0 + math.pi - ov * 0.5, a0 + 2 * math.pi + ov, w, colour, op, n // 2)


def cfill(pts, colour, op):
    if HAND:
        dx, dy = HAND * rnd.uniform(-0.08, 0.1), HAND * rnd.uniform(-0.06, 0.1)
        pts = [(x + dx + HAND * rnd.uniform(-0.03, 0.03), y + dy + HAND * rnd.uniform(-0.03, 0.03)) for x, y in pts]
    e = base("line")
    e["strokeColor"] = "transparent"
    e["backgroundColor"] = colour
    e["opacity"] = op
    e["polygon"] = True
    e["customData"] = {**e.get("customData", {}), "crisp": True}
    e["startBinding"] = e["endBinding"] = None
    e["startArrowhead"] = e["endArrowhead"] = None
    e["lastCommittedPoint"] = None
    els.append(place(e, pts + [pts[0]]))


def cell(cx, cy, rx, ry, colour, op, n=28):
    cfill(
        [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)],
        colour,
        op,
    )


def pdot(x, y, r, colour=INK, op=100):
    e = base("ellipse")
    e["strokeColor"] = "transparent"
    e["backgroundColor"] = colour
    e["opacity"] = op
    e["x"], e["y"], e["width"], e["height"] = x - r, y - r, 2 * r, 2 * r
    els.append(e)


def band(cx, ytop, ybot, rx, ry, n=16):
    """Visible side of a vertical cylinder between two ellipse centres: front arc at the bottom, front arc at the top."""
    return [
        (cx + rx * math.cos(math.pi - math.pi * i / n), ybot + ry * math.sin(math.pi - math.pi * i / n))
        for i in range(n + 1)
    ] + [(cx + rx * math.cos(math.pi * i / n), ytop + ry * math.sin(math.pi * i / n)) for i in range(n + 1)]


def knockout(pts):
    """Paper-white backing for a form that stands in front of lines behind it (draw it in the front layer, with OVER[0] = True)."""
    e = base("line")
    e["strokeColor"] = "transparent"
    e["backgroundColor"] = "#ffffff"
    e["opacity"] = 100
    e["polygon"] = True
    e["customData"] = {**e.get("customData", {}), "knockout": True}
    e["startBinding"] = e["endBinding"] = None
    e["startArrowhead"] = e["endArrowhead"] = None
    e["lastCommittedPoint"] = None
    els.append(place(e, pts + [pts[0]]))


def ell_full(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def prpoly(pts, r=1.0, w=0.6, colour=INK, op=100):
    """Ruled closed outline with exact rounded corners (screens, panels): two strokes that overlap at the joins."""
    n = len(pts)
    path = []
    for i in range(n):
        path += fillet(pts[i - 1], pts[i], pts[(i + 1) % n], r, 8)
    path.append(path[0])
    dense = []
    for a, b in itertools.pairwise(path):
        k = max(1, int(math.dist(a, b) / 0.4))
        dense += [(a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k) for t in range(k)]
    gx, gy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n

    def m_(p):
        dx, dy = p[0] - gx, p[1] - gy
        l = math.hypot(dx, dy) or 1
        return shade_mult(dx / l, dy / l)

    h = len(dense) // 2
    A = dense[: h + 4]
    B = dense[h - 2 :] + dense[:3]
    _stroke(A, w, colour, op, mult=[m_(p) for p in A])
    _stroke(B, w, colour, op, mult=[m_(p) for p in B])


# ---------------- shared geometry + parts ----------------
def bk(p: Point, d: float) -> Point:
    return (p[0] + d, p[1] - 0.7 * d)


def arc(cx, cy, rx, ry, a0, a1, n=18, **kw):
    pts = [
        (cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)
    ]
    ink_path(pts, **kw)


def ell_pts(cx, cy, rx, ry, k=10, rot=0.0):
    return [
        (cx + rx * math.cos(rot + 2 * math.pi * i / k), cy + ry * math.sin(rot + 2 * math.pi * i / k)) for i in range(k)
    ]


STEEL, STEEL_D, SHADE, COOL, GLASS, COPPER, COPPER_D = (
    "#ced4da",
    "#868e96",
    "#5c6b78",
    "#dbe4ea",
    "#a5d8ff",
    "#f08c00",
    "#c2410c",
)
ALU, ALU_L, DARK = "#dee2e6", "#f1f3f5", "#343a40"


def box(x0, y0, x1, y1, d, front=ALU, side=SHADE, top="#ffffff", fo=80, so=55, to=70, w=0.45, ink_op=100):
    """Rectangular block seen front-on with depth d going back up-right: front face true shape, top and right side faces."""
    cfill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], front, fo)
    cfill([(x1, y0), bk((x1, y0), d), bk((x1, y1), d), (x1, y1)], side, so)
    cfill([(x0, y0), bk((x0, y0), d), bk((x1, y0), d), (x1, y0)], top, to)
    # silhouette: one continuous stroke, corners rounded inside it, heavy on the shadow side (like the cabinet)
    r_ = min(0.45, (x1 - x0) * 0.15, (y1 - y0) * 0.15, d * 0.4)
    prpoly(
        [(x0, y1), (x0, y0), bk((x0, y0), d), bk((x1, y0), d), bk((x1, y1), d), (x1, y1)], r=r_, w=w * 1.25, op=ink_op
    )

    # edges between faces: thin, lighter, broken where the light hits them, joined softly into the silhouette
    def inner(p, q, k, gap):
        if gap:
            t1, t2 = rnd.uniform(0.35, 0.5), rnd.uniform(0.62, 0.75)
            m1 = (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)
            m2 = (p[0] + (q[0] - p[0]) * t2, p[1] + (q[1] - p[1]) * t2)
            pline(p, m1, w=w * k, op=int(ink_op * 0.7))
            pline(m2, q, w=w * k, op=int(ink_op * 0.7))
        else:
            pline(p, q, w=w * k, op=int(ink_op * 0.8))

    ins = 0.15  # stop short of the silhouette so joins read as soft
    inner((x0 + ins, y0), (x1 - ins * 0.5, y0), 0.45, True)  # top-front edge: catches the light
    inner((x1, y0 + ins * 0.5), (x1, y1 - ins), 0.6, False)  # front-side edge: turns into shadow
    inner((x1 + ins * 0.6, y0 - ins * 0.42), bk((x1, y0), d - ins), 0.4, True)  # top-side edge


def tube(p, q, wid=0.9, col=ALU):
    L_ = math.dist(p, q) or 1
    nx_, ny_ = -(q[1] - p[1]) / L_ * wid / 2, (q[0] - p[0]) / L_ * wid / 2
    a_, b_, c_, d_ = (
        (p[0] + nx_, p[1] + ny_),
        (q[0] + nx_, q[1] + ny_),
        (q[0] - nx_, q[1] - ny_),
        (p[0] - nx_, p[1] - ny_),
    )
    cfill([a_, b_, c_, d_], col, 85)
    cfill(
        [(p[0] + nx_ * 0.2, p[1] + ny_ * 0.2), (q[0] + nx_ * 0.2, q[1] + ny_ * 0.2), c_, d_], SHADE, 40
    )  # underside in shade
    pline(d_, c_, w=0.55)
    pline(a_, b_, w=0.25)
    pline(
        (p[0] - nx_ * 0.45, p[1] - ny_ * 0.45), (q[0] - nx_ * 0.45, q[1] - ny_ * 0.45), w=0.15, colour="#ffffff", op=90
    )


def vcyl(cx, yt, yb, rx, ry, col=ALU, dark=SHADE, top=ALU_L, fo=85, w=0.5, knock=False, ink_op=100, cap=True):
    """Vertical cylinder in the oblique view: top ellipse, side band; lit band left, core shadow right of centre,
    reflected light at the right edge; ink heavy on the right, light on the left."""
    if knock:
        knockout(band(cx, yt, yb, rx, ry))
        knockout(ell_full(cx, yt, rx, ry))
    cfill(band(cx, yt, yb, rx, ry), col, fo)
    cfill(
        [
            (cx + rx * 0.15, yt + ry * 0.9),
            (cx + rx * 0.7, yt + ry * 0.7),
            (cx + rx * 0.7, yb + ry * 0.7),
            (cx + rx * 0.15, yb + ry * 0.95),
        ],
        dark,
        45,
    )  # core shadow
    cfill(
        [
            (cx - rx * 0.62, yt + ry * 0.75),
            (cx - rx * 0.35, yt + ry * 0.9),
            (cx - rx * 0.35, yb + ry * 0.9),
            (cx - rx * 0.62, yb + ry * 0.75),
        ],
        "#ffffff",
        70,
    )  # lit band
    if cap:
        cell(cx, yt, rx, ry, top, fo)
        pell(cx, yt, rx, ry, w=w * 0.8, op=ink_op)
    parc(cx, yb, rx, ry, 0, math.pi, w=w * 1.1, op=ink_op)
    pline((cx - rx, yt), (cx - rx, yb), w=w * 0.75, op=ink_op)
    pline((cx + rx, yt), (cx + rx, yb), w=w * 1.3, op=ink_op)


def ecyl(x0, x1, y0, y1, col=ALU, dark=SHADE, fo=85, w=0.5, ends=True, ink_op=100):
    """Cylinder seen side-on in elevation (2D): flat rectangle that reads round through value bands:
    a white lit strip near the left, mid-tone body, core shadow right of centre, a sliver of reflected light at the right edge."""
    W_ = x1 - x0
    cfill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], col, fo)
    cfill([(x0 + W_ * 0.52, y0), (x0 + W_ * 0.86, y0), (x0 + W_ * 0.86, y1), (x0 + W_ * 0.52, y1)], dark, 45)
    cfill([(x0 + W_ * 0.14, y0), (x0 + W_ * 0.3, y0), (x0 + W_ * 0.3, y1), (x0 + W_ * 0.14, y1)], "#ffffff", 75)
    pline((x0, y0), (x0, y1), w=w * 0.7, op=ink_op)
    pline((x1, y0), (x1, y1), w=w * 1.35, op=ink_op)
    if ends:
        pline((x0, y0), (x1, y0), w=w * 0.6, op=ink_op)
        pline((x0, y1), (x1, y1), w=w * 1.1, op=ink_op)


def eblock(x0, y0, x1, y1, col=ALU, fo=80, w=0.5, r=0.4, ink_op=100, bevel=True):
    """A block in elevation (2D): front face only; it still reads solid through a lit top/left bevel strip,
    a shaded bottom/right strip and an outline heavy on the shadow side."""
    cfill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], col, fo)
    if bevel:
        b_ = min(0.6, (y1 - y0) * 0.18, (x1 - x0) * 0.18)
        cfill([(x0, y0), (x1, y0), (x1 - b_, y0 + b_), (x0 + b_, y0 + b_)], "#ffffff", 75)
        cfill([(x1, y0), (x1, y1), (x1 - b_, y1 - b_), (x1 - b_, y0 + b_)], SHADE, 45)
        cfill([(x0, y1), (x1, y1), (x1 - b_, y1 - b_), (x0 + b_, y1 - b_)], SHADE, 35)
    prpoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], r=r, w=w, op=ink_op)


def ground(x0, x1, y, depth=6, spread=10, oblique=True):
    """Ground shadow: falls right (and back in 3D), darker right under the object."""
    if oblique:
        wash(
            [
                (x0 - 1, y + 0.5),
                (x1, y + 1),
                bk((x1, y), depth),
                (bk((x1, y), depth)[0] + spread, bk((x1, y), depth)[1] + 1),
                (x1 + spread * 0.6, y + 5),
                (x0 + 2, y + 6),
            ],
            "#868e96",
            16,
            layers=2,
        )
        wash(
            [(x0, y + 0.3), (x1, y + 0.6), (x1 + 3, y - 1), (x1 + 4, y + 1.5), (x1 - 1, y + 3), (x0 + 1, y + 3)],
            "#495057",
            22,
            layers=1,
        )
    else:
        wash(
            [(x0 - 2, y + 0.4), (x1 + spread, y + 0.4), (x1 + spread - 3, y + 4.5), (x0, y + 4.5)],
            "#868e96",
            16,
            layers=2,
        )
        wash([(x0, y + 0.2), (x1 + 2, y + 0.2), (x1, y + 2.4), (x0 + 1, y + 2.4)], "#495057", 22, layers=1)


def splatter(cx, cy, r0, r1, n=10, bbox=None, cols=None):
    cols = cols or [INK, INK, "#495057", "#1c7ed6"]
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        rr = rnd.uniform(r0, r1)
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.85
        if bbox and bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            continue
        dot(x, y, rnd.uniform(0.3, 0.7), rnd.choice(cols), op=rnd.choice([100, 80]))


@contextlib.contextmanager
def recess() -> Generator[None]:
    """Draw the edges of a recess (a door set into a frame, a pocket): the frame shades its top and left
    inner edges, so line weight flips to the top left, strongly."""
    global LIGHT_AWAY, LW
    saved = LIGHT_AWAY, LW
    LIGHT_AWAY, LW = (-0.6, -0.8), 0.85
    try:
        yield
    finally:
        LIGHT_AWAY, LW = saved


# ---------------- 3D (oblique) helpers ----------------
def P(x: float, y: float, z: float = 0.0) -> Point:
    """Oblique projection: front faces keep their true shape, depth z runs back up-right."""
    return (x + z, y - 0.7 * z)


def bigbox(x0, x1, y0, y1, z0, z1, front=STEEL, fo=15, r=3.0, w=1.0, soft_edges=True, top_breath=True, closed=False):
    """Big 3D form: loose watercolour washes and a loose rounded silhouette (like a machine cabinet).
    x0..x1 wide, y0..y1 tall (y1 is the floor), z0..z1 deep. closed=True draws the bottom edge, for a box that
    does not stand on the floor."""
    F = [P(x0, y0, z0), P(x1, y0, z0), P(x1, y1, z0), P(x0, y1, z0)]
    wash(F, front, fo, layers=1)
    if not closed:  # darker toward the floor
        wash(
            [P(x0, y1 - (y1 - y0) * 0.2, z0), P(x1, y1 - (y1 - y0) * 0.2, z0), P(x1, y1, z0), P(x0, y1, z0)],
            STEEL_D,
            14,
            layers=1,
        )
    S = [P(x1, y0, z0), P(x1, y0, z1), P(x1, y1, z1), P(x1, y1, z0)]
    wash(
        S,
        SHADE,
        26,
        layers=2,
        pool=[
            P(x1, y0 + (y1 - y0) * 0.55, z0 + 0.5),
            P(x1, y0 + (y1 - y0) * 0.55, z1),
            P(x1, y1, z1),
            P(x1, y1, z0 + 0.5),
        ],
    )
    wash(
        [P(x1, y0, z1 - 1.2), P(x1, y0, z1), P(x1, y1, z1), P(x1, y1, z1 - 1.2)], "#ffffff", 35, layers=1
    )  # reflected light at the back edge
    if top_breath:
        wash(
            [
                P(x0 + (x1 - x0) * 0.3, y0, z1),
                P(x1, y0, z1),
                P(x1, y0, z1 - (z1 - z0) * 0.6),
                P(x0 + (x1 - x0) * 0.35, y0, z1 - (z1 - z0) * 0.5),
            ],
            "#e9ecef",
            30,
            layers=1,
        )
    rpoly(
        [P(x0, y1, z0), P(x0, y0, z0), P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x1, y1, z0)],
        r=r,
        w=w,
        closed=closed,
    )
    if closed:  # underside edge is in shadow: press it harder
        ink(P(x0 + r, y1, z0), P(x1 - r * 0.5, y1, z0), w=w * 0.9, over=(0, 0.6), restate=0.3, bow=0.3)
    if soft_edges:
        soft(P(x0 + r * 0.7, y0, z0), P(x1 - r * 0.6, y0, z0))
        soft(P(x1, y0 + r * 0.7, z0), P(x1, y1 - r * 0.6, z0))
        soft(P(x1, y0, z0 + r * 0.5), P(x1, y0, z1 - r * 0.5))


def obox(x0, x1, y0, y1, z0, d, **kw):
    """Precise small block in 3D world coordinates: box() with its front face at depth z0."""
    a = P(x0, y0, z0)
    b = P(x1, y1, z0)
    box(a[0], a[1], b[0], b[1], d, **kw)


# ---------------- 2D (front elevation) helpers ----------------
def big2d(x0, y0, x1, y1, front=STEEL, fo=16, r=2.6, w=1.0, floor=False, turn=0.1):
    """Big form in elevation, loose: washes for the face, a darker band toward the floor, a shaded band where the
    rounded right corner turns away, a lit strip along the top, then a loose rounded outline restated on the shadow side."""
    W_, H_ = x1 - x0, y1 - y0
    wash([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], front, fo, layers=1)
    wash([(x0, y1 - H_ * 0.22), (x1, y1 - H_ * 0.22), (x1, y1), (x0, y1)], STEEL_D, 12 if floor else 9, layers=1)
    tx_ = x1 - W_ * turn
    wash(
        [(tx_, y0 + r * 0.4), (x1, y0 + r), (x1, y1 - r * 0.5), (tx_, y1)],
        SHADE,
        22,
        layers=2,
        pool=[
            (x1 - W_ * turn * 0.45, y0 + H_ * 0.5),
            (x1, y0 + H_ * 0.5),
            (x1, y1 - r * 0.5),
            (x1 - W_ * turn * 0.45, y1),
        ],
    )
    wash(
        [(x0 + r, y0 + 0.4), (x1 - W_ * turn, y0 + 0.4), (x1 - W_ * turn, y0 + 1.6), (x0 + r, y0 + 1.8)],
        "#ffffff",
        45,
        layers=1,
    )
    rpoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], r=r, w=w * 0.85, closed=True)
    ink((x0 + r, y1), (x1 - r * 0.6, y1), w=w * 0.95, over=(0, 0.6), restate=0.3, bow=0.3)  # shadow side pressed harder
    ink((x1, y0 + r), (x1, y1 - r * 0.6), w=w * 0.9, over=(0, 0.6), restate=0.3, bow=0.3)
    pline(
        (tx_, y0 + r * 0.9), (tx_ - 0.2, y0 + (y1 - y0) * 0.45), w=0.22, colour="#868e96", op=55
    )  # where the corner starts to turn: faint, broken
    pline((tx_ - 0.2, y0 + (y1 - y0) * 0.58), (tx_ - 0.3, y1 - r * 0.7), w=0.26, colour="#868e96", op=65)


def save(item_id: str, name: str, out: str) -> int:
    """Write the sketch as an Excalidraw library item; return how many elements it holds."""
    item = {"id": item_id, "status": "published", "created": 1, "name": name, "elements": els}
    with open(out, "w") as f:
        json.dump({"libraryItems": [item]}, f)
    return len(els)
