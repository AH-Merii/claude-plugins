<p align="center">
  <img src="docs/logo.svg" width="168" alt="Field Notes logo: a sketchbook and a watercolour brush, drawn in ink and wash">
</p>

<h1 align="center">field-notes</h1>

<p align="center">
  A Claude Code skill that redraws photos, machines and icons as hand-drawn<br>
  urban-sketch ink and watercolour, and renders them to SVG.
</p>

## Examples

<table>
  <tr>
    <th width="50%">Photo</th>
    <th width="50%">Field Notes</th>
  </tr>
  <tr>
    <td><img src="docs/examples/skyline-photo.jpg" alt="Photo of the Abu Dhabi skyline from the water"></td>
    <td><img src="docs/examples/skyline.svg" alt="The Abu Dhabi skyline in ink and wash"></td>
  </tr>
  <tr>
    <td><img src="docs/examples/gripper-photo.jpg" alt="Photo of a robot arm's gripper lifting a blue towel"></td>
    <td><img src="docs/examples/gripper.svg" alt="The robot arm and gripper in ink and wash"></td>
  </tr>
  <tr>
    <td><img src="docs/examples/humanoid-photo.jpg" alt="Photo of a black humanoid robot on an orange backdrop"></td>
    <td><img src="docs/examples/humanoid.svg" alt="The humanoid robot in ink and wash"></td>
  </tr>
</table>

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

## Tests

```sh
python3 -m unittest discover -s plugins/field-notes/tests
```

They need only Python: Node and npm are faked.
