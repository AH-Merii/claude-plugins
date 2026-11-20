# field-notes

A skill for drawing icons and illustrations in the **Field Notes** style: urban-sketch line and
wash, with loose ink and watercolour for big forms, careful hand-drawn precision for small
mechanical parts, and line weight that follows light from the upper left. Every subject comes in
two views, a 2D front elevation and a 3D oblique.

![A stator winding machine in the Field Notes style](skills/field-notes/examples/winding_machine.jpg)

![A benchtop press in 2D and 3D](skills/field-notes/examples/press.jpg)

The agent picks it up when it draws in this style or converts something to it, for example "draw
this machine in the Field Notes style", "convert this icon to line and wash" or "make the 3D
version". The skill brings the rules that came out of review: what to take from a reference photo,
the real thing and the original icon, where to be loose and where to be precise, how 2D gets depth
without receding faces, how to keep parts in front of the ink behind them, and a part-by-part
check before handing a drawing over.

It also ships **inkwash**, the toolkit that draws the style. A drawing is a small Python body file
that uses the marks in `kit.py`. `inkwash.py build` turns it into a sketch, renders that to an SVG
with pressure-sensitive strokes ([perfect-freehand](https://github.com/steveruizok/perfect-freehand))
and watercolour SVG filters, and saves a PNG preview through Playwright's Chromium. It also renders
before-vs-after sheets and zoomed crops for checking parts. The SVGs are self-contained, so they
can go straight into a page, a design tool or Excalidraw.

## Prerequisites

- Python 3.10 or newer.
- Node.js 20 or newer with npm, and network access the first time.
  `python3 <skill-dir>/scripts/inkwash.py setup` installs perfect-freehand and Playwright with its
  Chromium into `~/.cache/field-notes/node`, or `$FIELD_NOTES_NODE_DIR`; a build does it by itself
  when they are missing.
- For portraits and busy photo scenes only, [uv](https://docs.astral.sh/uv/): `paint_trace.py`
  runs with OpenCV and numpy that `uv run --with` brings in.

## Install

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install field-notes@ah-merii
```

The skill appears as `field-notes:field-notes`. Claude loads it when a task matches; you can also
call it directly with `/field-notes:field-notes`.

## Examples

`skills/field-notes/examples/before-after/` holds the example set the agent samples from: each
image shows an original next to its approved Field Notes version (a winding machine, a relay
array, a copper coil, a lock, a cloud and a person), plus a press drawn from a photo and a
database. The relay array is the paint target. `skills/field-notes/examples/` also holds the
body files for the winding machine and the press, and `traced_photo.py`, which draws a portrait
or busy photo scene from the output of `scripts/paint_trace.py` (the skill's "Complex images"
section). To build one:

```sh
python3 plugins/field-notes/skills/field-notes/scripts/inkwash.py build \
  plugins/field-notes/skills/field-notes/examples/winding_machine.py --out /tmp/field-notes
```

## Tests

```sh
python3 -m unittest discover -s plugins/field-notes/tests
```

They need only Python: Node and npm are fakes that log their calls. They check that every example
builds the same sketch for a seed, that the kit marks what the renderer layers, that line weight
follows the light, and that the Node steps run with the cached packages. The real renderer is
checked by building an example as above.
