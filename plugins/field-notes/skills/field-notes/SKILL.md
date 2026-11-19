---
name: field-notes
description: Draw or convert icons and illustrations in the Field Notes style, a hand-drawn urban-sketch "line and wash" look. It uses loose ink and watercolour for big forms, careful hand-drawn precision for small mechanical parts, and line weight that follows light from the upper left. Each subject comes in a 2D front elevation and a 3D oblique view. Use it whenever you draw a new icon or illustration in this style, redraw an existing icon or a reference photo in it, or add the missing 2D or 3D view of a subject. Typical asks are "draw this machine in the Field Notes style", "convert this icon to line and wash", "make the 3D version", "make it look hand-drawn, ink and watercolour", and "match the winding machine". It ships its own toolkit, inkwash, which builds the SVG and a PNG preview.
---

# Field Notes

Field Notes is an urban-sketch **line and wash** style: loose ink and watercolour for big forms,
careful hand-drawn precision for small mechanical parts. **inkwash** is the toolkit that draws it.
Its files keep that name. Everything sits next to this file, in `<skill-dir>` (the skill's base
directory):

- `scripts/kit.py`, the drawing kit. A body file imports its marks and draws with them.
- `scripts/inkwash.py`, the build script: body file → sketch JSON → SVG → PNG preview, plus
  previews side by side and zoomed crops.
- `scripts/render.js`, `prev.js` and `crop.js`, the Node steps it runs. They use perfect-freehand
  for the pen strokes, SVG filters for the watercolour, and Playwright's Chromium for the PNGs.
- `examples/`, worked examples with their images, and `references/kit.md`, the kit's full API.

Read this whole file before drawing. Then study the examples:

- `examples/winding_machine.py` is the approved reference: 3D oblique and very detailed. Its
  image is `examples/winding_machine.jpg`. Match its overall finish.
- `examples/press_3d.py` and `examples/press_2d.py` show one machine converted from a reference
  photo, in 3D and in 2D. Their image is `examples/press.jpg`.

## Setup

Run `python3 <skill-dir>/scripts/inkwash.py setup` once. It needs Python 3.10 or newer, Node.js 20
or newer with npm, and network access the first time. The Node packages and Chromium go to
`~/.cache/field-notes/node` (or `$FIELD_NOTES_NODE_DIR`), never into the skill folder. A build
also installs the packages by itself when they are missing or out of date.

## Workflow

1. **Find the source of truth** (below), and gather it before you draw.
2. **Draw** one body file per view, in a working folder of your own, never in `<skill-dir>`.
   Build, look at the preview, and redraw until it reads.
3. **Verify** part by part (below) before you hand anything over.
4. **Draw both views.** Every subject gets a 2D front elevation and a 3D oblique view. Keep the
   original icon's view and add the missing one. Flat graphic subjects (markers, drawings,
   screens) get a 3D version as the sheet or screen seen obliquely.

## Source of truth, in this order

1. **The reference photo**, when there is one. Draw the thing in the photo: its parts, their
   shapes, proportions and placement. Crop and enlarge the photo to read each part.
2. **Look the real thing up** (WebSearch, WebFetch) for anything the photo doesn't show clearly,
   or when there is no photo: what the parts really are, how they attach, what a screen shows,
   what the controls are. Real details make it believable.
3. **The original icon** tells you only which subject and which view. When a photo exists, the
   photo wins over the icon everywhere. Without a photo, look the real thing up and draw that;
   never copy the icon's simplifications. One exception: a workpiece that tells the story, such as
   a part under a press, may be drawn **larger than true scale** for clarity, close to the size the
   original icon gave it.

**Don't invent parts.** No extra machines or sub-parts (stack lights, light curtains, motors on
top) unless the photo shows them; invented parts were rejected in review. Where the photo clearly
shows a part, draw only what it shows.

## Style rules

Each of these came from review feedback.

- **Know where to squiggle and where to be precise.** Big silhouettes, cabinets and washes are
  loose (`rpoly`, `ink`, `wash`, `soft`). Small, repeated, mechanical or aligned parts (buttons,
  lamps, screws, louvres, coils, screens, anything on an axis) get a precise **position** but still
  a hand-drawn line (`pline`, `parc`, `pell`, `prpoly`, `cfill`, `cell`). Imperfect is fine; sloppy
  (misaligned dots, wobbly rows) is not.
- **Line weight follows light**, which comes from the upper left. Ink is heavier on the shadow side
  (bottom and right edges), lighter on lit edges (top and left), thinnest on edges between faces,
  and broken where light hits. Recesses flip it, so their top and left edges are heavier: draw them
  inside `with recess():`. Pass `normal=` to `pline`; `parc`, `pell` and `prpoly` already weight
  by direction.
- **Round corners inside one continuous stroke** (`prpoly`, `rpoly`), never two lines meeting at a
  joint.
- **No copy-paste repeats.** Vary repeated parts in size, fullness, light, state (a lamp on or
  off, a spool full or used) and stroke pressure.
- **Don't over-line.** Suggest texture (windings, fins, grooves) with a few lines, pressed on the
  shadow side and fading toward the light.
- **Small accents stay quiet.** E-stops and buttons are small and shallow, with no loud plates;
  nothing "in your face".
- **Perspective matches the plane.** On a frontal face, circles are true circles, and things
  protrude along the depth axis.
- **Nothing hovers.** Show mounts, arms, cables and feet.
- **Screens show believable content,** such as a force-travel curve, readouts or a status.
- **Give parts real form** (core shadow, lit band, reflected light), so nothing looks like a flat
  sticker.
- **Small parts need a finer pen** (a lower `w`); heavy ink swamps them.
- **Round parts must read round in 2D.** A cylinder seen side-on becomes a box unless it gets
  value bands: lay a pale base coat, paint the colour and the core shadow over it, leave a lit band
  bare left of centre, keep reflected light at the right edge, round the corners slightly, and let
  lines that wrap the part (layer lines, lettering) curve with it. `ecyl` does the bands.
- **Text always reads upright,** even on a part that sits upside down. At icon size, upside-down
  text reads as a mistake.
- **Loads look like production.** Parts in ovens, trays and racks sit in neat, evenly spaced grids,
  all the same size and orientation; vary only light and finish. Put in a machine only what really
  goes in it at that process step.
- **Add character:** cast shadows (falling right and down, and back in 3D), a ground shadow,
  wet-in-wet blooms, granulation, a little splatter outside the drawing, white-gel highlights on
  lit edges, and a few loose flicks.

## 3D and 2D

- **3D is oblique:** `P(x, y, z) = (x + z, y - 0.7 z)`. Front faces keep their true shape; the top
  and the right side show. Use `bigbox` for loose big forms, `box` and `obox` for precise small
  blocks, `vcyl` for vertical cylinders, and `band` and `ell_full` for their outlines.
- **2D is a front elevation,** with no receding faces. Depth comes from overlap, cast shadows that
  fall right and down onto things behind, value bands on round forms (`ecyl`), bevel strips on
  blocks (`eblock`), a darker band toward the floor, heavier ink on the bottom and right, a flat
  ground shadow (`ground(..., oblique=False)`) and a few quick hatches in deep shade. Use `big2d`
  for big forms.
- **Keep the two views consistent:** the same parts, colours and proportions.

## Occlusion

The renderer lays every wash under all the ink, so anything that stands in front of earlier ink
goes in the front layer:

- Set `OVER[0] = True` before drawing a form that stands in front of earlier ink, and put a
  paper-white `knockout(polygon)` under each such form first. Draw back to front. Set
  `OVER[0] = False` again before the character section.
- A part hidden behind another must not show: start it where it emerges. For example, a spindle
  starts at the head's underside edge.
- A big box that floats instead of standing on the floor needs `closed=True`, so its bottom edge
  is drawn.

## Drawing with the kit

A body file is plain Python that imports what it draws with from `kit`; `inkwash.py` puts `kit`
on the path. Coordinates are world units with y pointing down; an icon is about 100 units across.

```python
"""Bench grinder, 3D: from the reference photo; wheel guard and tool rest looked up."""

from kit import OVER, P, bigbox, ground, knockout, splatter, vcyl, wash

NAME = "Bench grinder (3D)"  # optional; defaults to the file name

ground(P(20, 80)[0], P(70, 80)[0], P(70, 80)[1], depth=20, spread=12)
bigbox(20, 70, 50, 80, 0, 20)  # big forms first: washes go under the ink
OVER[0] = True  # parts that stand in front of earlier ink
knockout(...)
vcyl(...)
OVER[0] = False
splatter(45, 45, 44, 54, n=10, bbox=(8, 0, 90, 90))  # character last
```

Build it, and keep the outputs out of `<skill-dir>`:

```sh
W=<skill-dir>/scripts/inkwash.py
python3 $W build grinder_3d.py --out out                       # out/grinder_3d.{sketch.json,svg,png}
python3 $W build grinder_3d.py --out out --compare original.svg # before (left) vs after
python3 $W preview out/both.png out/grinder_2d.svg out/grinder_3d.svg
python3 $W crop out/grinder_3d.svg out/crop.png X Y W H         # zoom into world coordinates
```

`build` takes `--seed` (the hand, default 7), `--stroke` (base stroke width, default 0.1), `--px`
(SVG width, default 1400), `--paper` (a paper background; leave it off for icons, which are
transparent) and `--no-preview`. Read the PNGs to look at them. The SVG's `viewBox` gives the world
coordinates for `crop`.

The marks, forms, colours and their parameters are in [references/kit.md](references/kit.md).
Gotchas:

- **Fills multiply,** like glazes. A fill over a dark fill gets darker, so knock out first. A white
  or pale highlight over a colour is invisible: put a paper-white `knockout` under the highlight,
  or lay a pale base coat first and paint the colour and shadow over it, leaving the lit band
  bare.
- **Very short `_stroke`s with corners turn into blobs.** Draw a small rectangle as four separate
  strokes with `taper=False`.
- **Keep fills inside their outline.**

## Verify before you hand anything over

Mistakes slipped through here, so do every step:

1. **Part by part against the photo.** Crop the reference and your drawing at the same part and
   look at them side by side. Same shape, same count, same placement? A spindle drawn as three
   shrinking cylinders read as a nozzle; the photo showed one tube.
2. **Read test.** At full-view size, ask of every part what it reads as. If the answer isn't the
   real part, redraw it.
3. **Occlusion test.** Nothing behind shows through, nothing floats, and every edge that should
   exist is drawn.
4. **Style test.** Line weights vary with light, repeats are varied, small parts are precise, big
   forms are loose and accents are quiet.
5. **Finish.** Compare with `examples/winding_machine.jpg` for overall finish, and check that both
   views exist and match.
