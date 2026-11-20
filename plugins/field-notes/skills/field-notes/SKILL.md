---
name: field-notes
description: Draw or convert icons and illustrations in the Field Notes style, a hand-drawn urban-sketch "line and wash" look. It uses loose ink and watercolour for big forms, careful hand-drawn precision for small mechanical parts, and line weight that follows light from the upper left. Each subject comes in a 2D front elevation and a 3D oblique view. Use it whenever you draw a new icon or illustration in this style, redraw an existing icon or a reference photo in it, or add the missing 2D or 3D view of a subject. Typical asks are "draw this machine in the Field Notes style", "convert this icon to line and wash", "make the 3D version", "make it look hand-drawn, ink and watercolour", and "match the winding machine". It ships its own toolkit, inkwash, which builds the SVG and a PNG preview.
argument-hint: "[inspiration-dir]"
---

# Field Notes

Field Notes is an urban-sketch **line and wash** style: loose ink and watercolour for big forms,
careful hand-drawn precision for small mechanical parts. **inkwash** is the toolkit that draws it.
Its files keep that name. Everything sits next to this file, in `<skill-dir>` (the skill's base
directory):

- `scripts/kit.py`, the drawing kit. A body file imports its marks and draws with them.
- `scripts/inkwash.py`, the build script: body file → sketch JSON → SVG → PNG preview, plus
  previews side by side and zoomed crops.
- `scripts/paint_trace.py`, the paint-then-trace step for portraits and busy photo scenes (below).
- `scripts/render.js`, `prev.js` and `crop.js`, the Node steps it runs. They use perfect-freehand
  for the pen strokes, SVG filters for the watercolour, and Playwright's Chromium for the PNGs.
- `examples/`, the example set and the worked examples, and `references/kit.md`, the kit's full
  API.

Read this whole file before drawing. Then open and look at every image in the example set below.

## The example set: sample from these

These are the approved results. Each image in `examples/before-after/` shows the original on the
left and the approved Field Notes version on the right. Sample your look from these and nothing
else: not from older versions, and not from your own earlier drawings.

| Image | What it teaches |
|-------|-----------------|
| `winding-machine.jpg` | A rough 3D icon → the approved 3D reference: very detailed, the overall finish to match |
| `relay-array.jpg` | **The paint target.** Mostly paper, one light wash per material, darker colour only as shadow pooled to the lower right |
| `copper-coil.jpg` | Painting in parts: separate turns, each with its own tone |
| `lock.jpg` | A flat library symbol drawn freehand, its paint laid as visible strokes |
| `cloud.jpg` | An angular library outline turned into a soft freehand shape with light washes |
| `person.jpg` | A symbol given round form with layered washes and a few hatches |
| `press.jpg` | No original icon: a reference photo → 2D and 3D |
| `database.jpg` | No before: round form, value bands, hand-drawn details |

`examples/winding_machine.py`, `examples/press_3d.py` and `examples/press_2d.py` are the body
files behind the winding machine and the press, so you can see how the kit draws them.

**Check against the set before you hand anything over.** Put your drawing next to the closest
example and next to the relay array, and compare paint, ink and finish. If yours is heavier,
greyer, flatter or more polished than they are, redraw it.

## Optional inspiration folder

Inspiration folder for this run (empty when none was given): `$ARGUMENTS`

The skill takes an optional folder of extra inspiration images, such as urban-sketching drawings
of buildings in line and wash: `/field-notes <dir>`. When one is given, open every image in it
before drawing. They set the mood and the hand of the style; the example set above still sets the
finish. Take these from them, and nothing that contradicts the style rules below:

- **Ink that flows.** Lines wobble, overshoot corners, double up and break; no ruler-straight,
  machine edges anywhere.
- **Real watercolour, not marker.** Washes bleed past the ink, pool darker at the bottom and
  shadow side, leave paper showing in the light, and fade out loosely instead of stopping at a
  hard edge. Marker is only for the dark accents.
- **Detail where it counts.** Small parts are drawn with care; big surfaces stay loose and mostly
  paper.
- **Life around the form:** a few splatter specks, drips and loose hatches, never tidy fills.

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
4. **Draw both views** when asked for them. A machine or part gets a 2D front elevation and a 3D
   oblique view: keep the original icon's view and add the missing one. Flat graphic subjects
   (markers, drawings, analysis plots) and library symbols stay in their original single view.

## Source of truth, in this order

1. **The reference photo**, when there is one. Draw the thing in the photo: its parts, their
   shapes, proportions and placement. Crop and enlarge the photo to read each part. A portrait or
   a busy photo scene goes through **Complex images** below instead.
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

## Complex images: paint, then trace

Portraits, people and busy photo scenes lose their likeness when built from hand-placed marks, and
a direct trace of the photo picks up its texture. Paint the photo flat as ink and wash first, then
trace that painting into kit marks. Machines, parts and icons stay hand-drawn from the source of
truth, and library symbols keep their own rule (**Library shapes only guide symbols**).

1. **Mark each face** as an ellipse in photo pixels, `CX,CY,RX,RY` (centre, then radii). Ink inside
   it keeps the photo's own eyes, nose and mouth; everywhere else the ink follows the flat colour
   edges.
2. **Paint and trace.** It needs `uv`; OpenCV and numpy come in through `--with`:

   ```sh
   uv run --no-project --with opencv-contrib-python-headless --with numpy \
     python <skill-dir>/scripts/paint_trace.py photo.png --out out --face 305,515,95,95 --face 750,500,130,150
   ```

   It writes `out/painted.png`, the flat ink-and-wash painting, and `out/trace.json`: wash regions
   light to dark and pen paths longest first, in world units of photo px / 10.
3. **Look at `out/painted.png`.** The drawing can't read better than the painting: a face that is
   off here stays off, so move or resize its ellipse and rerun.
4. **Build the traced body:**
   `TRACE=out/trace.json python3 <skill-dir>/scripts/inkwash.py build <skill-dir>/examples/traced_photo.py --out out`.
   It lays the ink as untapered strokes and the washes light to dark, with greys lightened so the
   paper shows. To tune it or add hand-drawn marks on top, copy it into your working folder first.

Then verify as for any drawing, part by part against the photo.

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
- **Paint like the relay array.** Mostly paper: one light wash per material, paper left bare on
  the lit upper left, and darker colour only as pooled shadow under and to the lower right of
  parts. Never washed out: true colours and values still read, and black stays black. The lit side
  lifts gradually, never bleached by one hard diagonal.
- **Light comes from varied strokes, not faded fills.** Lay washes as several visible brush
  strokes that follow the form and vary in tone, width and where they stop, with small paper gaps
  between them. A light area reads light because its strokes are fewer, paler and broken. Use two
  or three tones of the subject's own colour. Keep this subtle on small solid parts, where heavy
  strokes turn grungy.
- **Library shapes only guide symbols.** When you convert a library icon (a lock, a cloud, a
  person), draw the symbol freehand in its spirit. Never trace its exact geometry, and soften shapes
  that are too angular. Keep its layout and bounding box so it still drops into diagrams.
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
5. **Against the example set.** Open the closest image in `examples/before-after/` and
   `relay-array.jpg`, and put your drawing next to them. Match their paint, ink and finish. Check
   that every view you were asked for exists and that the views match.
6. **Show the original next to it.** Every review sheet puts the original (or the photo) beside the
   new drawing, so the reviewer can judge the change.

## Running many drawings

When an orchestrator hands drawings to helper agents:

- **One subject per agent.** When a drawing is done, the next one goes to a brand new agent.
- **A redo goes to a new agent** that gets only the original and the written feedback, never the
  rejected version. An agent that has seen its own earlier attempts drifts toward them.
- **Same opening for every agent, for the prompt cache.** First send this skill alone and ask for a
  one-word acknowledgement. Then send the subject. Every agent's opening is then the same, so it is
  read from the cache after the first one.
- Agents work in parallel and don't see each other's work.
