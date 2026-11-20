"""Paint a photo flat as ink and wash, then trace that painting into wash regions and pen paths.

    uv run --no-project --with opencv-contrib-python-headless --with numpy python paint_trace.py \
        PHOTO --out DIR [--face CX,CY,RX,RY]... [--colours 16]

Writes to DIR:
  painted.png        the ink-and-wash raster: look at it before drawing from the trace
  painted_flat.png   the flattened colours under it
  painted_ink.png    the ink mask (white lines on black)
  trace.json         {w, h, washes, ink} in world units (photo px / 10), drawn by examples/traced_photo.py

--face marks an ellipse in photo pixels whose finer features (eyes, nose, mouth) come from the photo itself.
"""

import argparse
import json
import sys
from pathlib import Path

SCALE = 10.0  # photo px per world unit
N8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

Face = tuple[int, int, int, int]
Pixel = tuple[int, int]  # (y, x)


def parse_face(text: str) -> Face:
    try:
        cx, cy, rx, ry = (round(float(v)) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"wants CX,CY,RX,RY in photo pixels, got {text!r}") from None
    return cx, cy, rx, ry


# ---- step 1: paint ----------------------------------------------------------------------------


def _xdog(gray, s0, s1, k):
    """Black-on-white XDoG edges of a 0..1 grey image, as a 0/255 mask."""
    import cv2
    import numpy as np

    a = cv2.GaussianBlur(gray, (0, 0), s0)
    b = cv2.GaussianBlur(gray, (0, 0), s1)
    mask = ((a - k * b) < -0.010).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def paint(img, faces: list[Face]):
    """Flatten a BGR photo into (painted, flat, ink): pale flat colour regions with XDoG ink over them."""
    import cv2
    import numpy as np

    flat = img.copy()
    for _ in range(3):
        flat = cv2.bilateralFilter(flat, 9, 40, 9)
    flat = cv2.pyrMeanShiftFiltering(flat, 14, 28, maxLevel=2)
    flat = cv2.edgePreservingFilter(flat, flags=cv2.RECURS_FILTER, sigma_s=60, sigma_r=0.35)
    # wash: lift the values toward paper and keep the colour
    hsv = cv2.cvtColor(flat, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 2] = 255 - (255 - hsv[..., 2]) * 0.72
    hsv[..., 1] *= 0.9
    wash = cv2.cvtColor(hsv.clip(0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    # ink from the flattened image, so lines follow region edges, not texture
    ink = _xdog(cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255, 1.3, 2.1, 0.98)
    if faces:
        fine_grey = cv2.cvtColor(cv2.bilateralFilter(img, 5, 30, 5), cv2.COLOR_BGR2GRAY)
        fine = _xdog(fine_grey.astype(np.float32) / 255, 1.0, 1.6, 0.985)
        inside = np.zeros_like(ink)
        for cx, cy, rx, ry in faces:
            cv2.ellipse(inside, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
        ink = np.where(inside > 0, cv2.bitwise_or(ink, fine), ink)
    painted = wash.copy()
    painted[ink > 0] = (painted[ink > 0] * 0.15).astype(np.uint8)
    return painted, flat, ink


# ---- step 2: trace the washes -----------------------------------------------------------------


def washes(painted, colours: int = 16) -> list[dict]:
    """K-means colour regions of the painting as polygons, light to dark, as a painter lays them."""
    import cv2
    import numpy as np

    h, w = painted.shape[:2]
    small = cv2.medianBlur(cv2.resize(painted, (w // 2, h // 2), interpolation=cv2.INTER_AREA), 5)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    stop = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centres = cv2.kmeans(lab, colours, None, stop, 3, cv2.KMEANS_PP_CENTERS)
    labels = cv2.medianBlur(cv2.medianBlur(labels.reshape(small.shape[:2]).astype(np.uint8), 9), 7)
    bgr = cv2.cvtColor(centres.reshape(1, -1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR)[0]
    out = []
    for k in range(colours):
        mask = cv2.morphologyEx((labels == k).astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        b, g, r = (int(v) for v in bgr[k])
        for c in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            area = cv2.contourArea(c)
            poly = cv2.approxPolyDP(c, 1.0, True)[:, 0, :]
            if area < 180 or len(poly) < 3:
                continue
            out.append(
                {
                    "pts": [[round(float(x) * 2 / SCALE, 2), round(float(y) * 2 / SCALE, 2)] for x, y in poly],
                    "rgb": [r, g, b],
                    "lum": round(float(centres[k][0]) / 255, 3),
                    "area": round(area * 4 / SCALE / SCALE, 2),
                }
            )
    out.sort(key=lambda region: region["lum"], reverse=True)
    return out


# ---- step 3: trace the ink: skeleton -> pen paths ---------------------------------------------


def neighbours(on: set[Pixel], p: Pixel) -> list[Pixel]:
    """8-neighbours of p on the skeleton, skipping a diagonal step that an orthogonal neighbour already covers."""
    y, x = p
    out = []
    for dy, dx in N8:
        q = (y + dy, x + dx)
        if q not in on or (dy and dx and ((y + dy, x) in on or (y, x + dx) in on)):
            continue
        out.append(q)
    return out


def _walk(nb: dict[Pixel, list[Pixel]], used: set, p: Pixel, q: Pixel) -> list[Pixel]:
    path = [p, q]
    used.add(frozenset((p, q)))
    while len(nb[q]) == 2:
        nxt = [r for r in nb[q] if frozenset((q, r)) not in used]
        if not nxt:
            break
        used.add(frozenset((q, nxt[0])))
        q = nxt[0]
        path.append(q)
    return path


def skeleton_paths(on: set[Pixel]) -> list[list[Pixel]]:
    """Walk a one-pixel skeleton into paths that run from end or junction to end or junction; loops last."""
    nb = {p: neighbours(on, p) for p in on}
    used: set = set()
    paths = []
    for p in sorted(on, key=lambda p: (len(nb[p]) == 2, p)):
        for q in nb[p]:
            if frozenset((p, q)) not in used:
                paths.append(_walk(nb, used, p, q))
    return paths


def heading(path: list[Pixel], at_end: bool) -> tuple[float, float]:
    """Unit direction a path leaves by, at its end or (reversed) at its start."""
    seg = path[-6:] if at_end else path[5::-1]
    (y0, x0), (y1, x1) = seg[0], seg[-1]
    n = ((y1 - y0) ** 2 + (x1 - x0) ** 2) ** 0.5 or 1
    return (y1 - y0) / n, (x1 - x0) / n


def _continues(pi, hi, pj, hj, d: float) -> bool:
    """True when leaving one end points at the other end, and the other path carries on the same way."""
    dy, dx = (pj[0] - pi[0]) / (d or 1), (pj[1] - pi[1]) / (d or 1)
    toward = hi[0] * dy + hi[1] * dx if d > 1 else 1
    onward = -(hj[0] * dy + hj[1] * dx) if d > 1 else 1
    straight = -(hi[0] * hj[0] + hi[1] * hj[1])
    return toward > 0.6 and onward > 0.6 and straight > 0.6


def _join_candidates(paths, reach: float):
    ends = [(i, e, p[-1] if e else p[0], heading(p, bool(e))) for i, p in enumerate(paths) for e in (0, 1)]
    found = []
    for a, (i, ei, pi, hi) in enumerate(ends):
        for j, ej, pj, hj in ends[a + 1 :]:
            d = ((pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2) ** 0.5
            if i != j and d <= reach and _continues(pi, hi, pj, hj, d):
                found.append((d, i, ei, j, ej))
    return sorted(found)


def join_paths(paths: list[list[Pixel]], reach: float = 14, rounds: int = 4) -> list[list[Pixel]]:
    """Join broken lines: link path ends that nearly meet and keep heading the same way, nearest first."""
    paths = [p for p in paths if len(p) >= 3]
    for _ in range(rounds):
        merged: dict[int, list[Pixel]] = {}
        gone: set[int] = set()
        for _d, i, ei, j, ej in _join_candidates(paths, reach):
            if {i, j} & (gone | merged.keys()):
                continue
            head = paths[i] if ei == 1 else paths[i][::-1]
            tail = paths[j] if ej == 0 else paths[j][::-1]
            merged[i] = head + tail
            gone.add(j)
        if not merged:
            break
        paths = [merged.get(i, p) for i, p in enumerate(paths) if i not in gone]
    return paths


def ink_lines(ink, flat) -> list[dict]:
    """Pen paths along the ink mask, longest first, with the line's thickness and the darkness under it."""
    import cv2
    import numpy as np

    grey = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    thick = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    skeleton = cv2.ximgproc.thinning(cv2.dilate(ink, np.ones((3, 3), np.uint8)))
    on = {(int(y), int(x)) for y, x in zip(*np.nonzero(skeleton), strict=True)}
    out = []
    for path in join_paths(skeleton_paths(on)):
        if len(path) < 10:
            continue
        ys, xs = np.array(path).T
        poly = cv2.approxPolyDP(np.stack([xs, ys], 1).astype(np.int32).reshape(-1, 1, 2), 0.9, False)[:, 0, :]
        out.append(
            {
                "pts": [[round(float(x) / SCALE, 2), round(float(y) / SCALE, 2)] for x, y in poly],
                "len": round(len(path) / SCALE, 1),
                "thick": round(float(thick[ys, xs].mean()), 2),
                "dark": round(1 - float(grey[ys, xs].mean()), 2),
            }
        )
    out.sort(key=lambda s: s["len"], reverse=True)
    return out


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paint_trace.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("photo", help="the reference photo")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument(
        "--face",
        type=parse_face,
        action="append",
        default=[],
        metavar="CX,CY,RX,RY",
        help="a face ellipse in photo pixels: ink there keeps the photo's finer features (repeatable)",
    )
    p.add_argument("--colours", type=int, default=16, help="wash colours to quantise to (default 16)")
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    import cv2

    img = cv2.imread(args.photo)
    if img is None:
        sys.exit(f"paint_trace.py: can't read {args.photo}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    painted, flat, ink = paint(img, args.face)
    for name, image in (("painted", painted), ("painted_flat", flat), ("painted_ink", ink)):
        cv2.imwrite(str(out / f"{name}.png"), image)
    h, w = img.shape[:2]
    trace = {"w": w / SCALE, "h": h / SCALE, "washes": washes(painted, args.colours), "ink": ink_lines(ink, flat)}
    (out / "trace.json").write_text(json.dumps(trace))
    print(f"{out / 'trace.json'}: {len(trace['washes'])} wash regions, {len(trace['ink'])} ink paths")


if __name__ == "__main__":
    main()
