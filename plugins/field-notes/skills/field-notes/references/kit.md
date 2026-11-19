# kit.py reference

Every mark appends Excalidraw elements to `kit.els`; `inkwash.py build` resets the kit, runs the
body file and saves them. Points are `(x, y)` tuples in world units, y down. `w` is pen pressure
(relative weight), `op` is opacity 0–100, and `colour`/`col` is a hex string. Import what you use:
`from kit import OVER, P, bigbox, pline, ...`.

## Loose marks: big forms, washes, character

| Mark | What it draws |
|------|---------------|
| `ink(p, q, w=1.0, over=(1.5, 4.5), bow=1.0, restate=0.7, colour=INK, op=100)` | One pen stroke from p to q that overshoots both ends, bows a little and is sometimes restated. `over=(0, 0.6), restate=0` for a controlled edge. |
| `poly(pts, closed=True, **ink)` | `ink` along each edge of a polygon. |
| `ink_path(path, w=1.0, over=(0.4, 1.5), restate=0.5, ...)` | A pen stroke along a polyline, such as a curve you computed. |
| `rpoly(pts, r=3.5, closed=False, **ink_path)` | A loose contour whose corners are curves inside the strokes, never joints. The silhouette of big forms. |
| `soft(p, q, w=0.45, op=75)` | The inner edge of a rounded form: thin, broken, lighter. |
| `arc(cx, cy, rx, ry, a0, a1, n=18, **ink_path)` | A loose elliptical arc (angles in radians, y down). |
| `loop(cx, cy, rx, ry, w=0.9, ...)` | A loose ellipse drawn in one go, ends overlapping. |
| `wash(pts, colour, op=30, layers=2, pool=None)` | Watercolour: `layers` translucent blobs over the polygon; `pool` adds a darker blob where pigment collects. |
| `blob(pts, colour, op, wob=0.9, grow=0.0)` | One wash layer. |
| `granulate(pts, colour, n=25, op=45)` | Pigment specks across the polygon's bounding box. |
| `dot(x, y, r, colour=INK, op=100)` | A loose speck (splatter). |
| `splatter(cx, cy, r0, r1, n=10, bbox=None, cols=None)` | Splatter in a ring around the drawing, skipping anything inside `bbox` `(x0, y0, x1, y1)`. |
| `ground(x0, x1, y, depth=6, spread=10, oblique=True)` | The ground shadow, falling right (and back in 3D); `oblique=False` for 2D. |

## Precise marks: small, repeated, mechanical parts

Exact position, hand-drawn line. Line weight follows the light.

| Mark | What it draws |
|------|---------------|
| `pline(p, q, w=0.6, colour=INK, op=100, normal=None)` | A careful straight line. `normal` is the edge's outward unit normal, e.g. `(0, 1)` for a bottom edge: shadow-side edges press harder, lit edges lighter. |
| `parc(cx, cy, rx, ry, a0, a1, w=0.5, ...)` | A careful elliptical arc, weighted by direction. `0..pi` is the front (lower) half. |
| `pell(cx, cy, rx, ry, w=0.5, ...)` | A careful closed ellipse that meets itself exactly. |
| `prpoly(pts, r=1.0, w=0.6, ...)` | A careful closed outline with exact rounded corners (screens, panels), weighted by direction. |
| `_stroke(pts, w=0.6, colour=INK, op=100, taper=True, mult=None)` | The pen itself, along any point list. `taper=False` for screen text and bars; `mult` scales the weight point by point. |
| `cfill(pts, colour, op)` | Paint laid carefully inside a line: no bleed, just paper grain. |
| `cell(cx, cy, rx, ry, colour, op)` | A filled ellipse (`cfill`). |
| `pdot(x, y, r, colour=INK, op=100)` | An exact round dot: screws, LEDs. |
| `knockout(pts)` | Paper-white backing that hides the lines behind a form. Use it in the front layer. |

## Forms

| Form | View | What it draws |
|------|------|---------------|
| `P(x, y, z=0.0)` | 3D | Oblique projection: `(x + z, y - 0.7 z)`. |
| `bk(p, d)` | 3D | Point `p` moved `d` units back: `P` for a point already projected. |
| `bigbox(x0, x1, y0, y1, z0, z1, front=STEEL, fo=15, r=3.0, w=1.0, soft_edges=True, top_breath=True, closed=False)` | 3D | A big loose box: washed front, shaded side with reflected light at its back edge, a breath of grey on top, a loose rounded silhouette. `closed=True` draws the underside of a box that doesn't stand on the floor. |
| `box(x0, y0, x1, y1, d, front=ALU, side=SHADE, top='#ffffff', fo=80, so=55, to=70, w=0.45)` | 3D | A precise small block, front face at its true shape, depth `d` going back. |
| `obox(x0, x1, y0, y1, z0, d, **box)` | 3D | `box` in world coordinates, front face at depth `z0`. |
| `vcyl(cx, yt, yb, rx, ry, col=ALU, dark=SHADE, top=ALU_L, knock=False, cap=True)` | 3D | A vertical cylinder: top ellipse, lit band, core shadow, reflected light. `knock=True` knocks out what's behind it. |
| `band(cx, ytop, ybot, rx, ry)` | 3D | The visible side of a vertical cylinder, as a polygon. |
| `ell_full(cx, cy, rx, ry, n=28)`, `ell_pts(cx, cy, rx, ry, k=10, rot=0.0)` | both | Ellipse polygons for fills, knockouts and washes. |
| `tube(p, q, wid=0.9, col=ALU)` | both | A rod or arm from p to q with a shaded underside and a glint. |
| `big2d(x0, y0, x1, y1, front=STEEL, fo=16, r=2.6, w=1.0, floor=False, turn=0.1)` | 2D | A big loose form in elevation: a darker band toward the floor, a shaded band where the right corner turns away (`turn` is its share of the width), a lit strip on top. |
| `ecyl(x0, x1, y0, y1, col=ALU, dark=SHADE, ends=True)` | 2D | A cylinder seen side-on that reads round through value bands. |
| `eblock(x0, y0, x1, y1, col=ALU, bevel=True)` | 2D | A block in elevation that reads solid through bevel strips. |
| `fillet(a, b, c, r)` | both | The points of a rounded corner at b, for your own paths. |

## State

- `OVER[0] = True` puts what follows in the front layer, above all earlier ink; set it back to
  `False` before the character section.
- `with recess():` flips line weight to the top left for the edges of a recess (a door set in a
  frame, a pocket).
- `rnd` is the hand's random generator, seeded by `--seed`. Use it for variation
  (`rnd.uniform(...)`), never the `random` module, so a seed always draws the same picture.
- `HAND` (1.0) is how much a precise line wavers; 0 rules it. `LIGHT_AWAY` and `LW` set the light
  direction and how strongly weight follows it.

## Colours

`INK #1e1e1e`, `STEEL #ced4da`, `STEEL_D #868e96`, `SHADE #5c6b78`, `COOL #dbe4ea`,
`GLASS #a5d8ff`, `COPPER #f08c00`, `COPPER_D #c2410c`, `ALU #dee2e6`, `ALU_L #f1f3f5`,
`DARK #343a40`. The examples use the Open Color palette for everything else, e.g. `#495057` for
deep shade, `#1864ab` for screens, `#40c057` for green buttons and `#f03e3e` for red ones.

## Sketch format

`inkwash.py build` writes `{"libraryItems": [{"id", "name", "elements"}]}`, an Excalidraw library.
`render.js` reads it (or any JSON with an `elements` array): `freedraw` elements become ink,
closed `line` shapes with a fill become washes (or crisp fills and knockouts, by `customData`), and
`ellipse` elements become dots. Washes multiply over each other like glazes; ink sits above them,
and `customData.over` elements sit above everything, in drawing order.
