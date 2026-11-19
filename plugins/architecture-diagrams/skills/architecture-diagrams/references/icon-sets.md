# Icon sets

Use the first source that works, and say once which one is in use. Use one icon per concept
across all diagrams, and put each icon's label as separate text under it.

## 1. Custom icons

Icons the user supplied for concepts that no general set covers are used first for
whatever they cover.

## 2. The project's icon set

Where the project settings name one, or the user points to one. An icon set is a folder
with:

- **A catalogue** (`CATALOGUE.md` by default): which libraries exist and when to use each,
  plus any conventions for using them. Read it first. Use only the libraries the user named, or
  all of them if none.
- **A manifest** (`manifest.json` by default): one entry per icon. Search it for every
  element before drawing, and read only the entries for the icons you place, never the
  whole file.
- **The icons themselves:** SVG files, Excalidraw library files (`.excalidrawlib`), or both.
- **Optionally a README** that defines the colours per element type and their licences.

### Manifest entry

The manifest is a JSON array (or an object with an `icons` array) of entries. Only `key`
and `label` are required; the rest says how the icon can be placed.

| Field | Meaning |
| --- | --- |
| `key` | Unique id, used in the catalogue and in `.excalidrawlib` items as `lib-<key>` |
| `label` | The name shown under the icon |
| `category` or `group` | For browsing only |
| `source` | Where it came from, e.g. `lucide:database` |
| `center` | `{x, y}`: the visual centre, to align by instead of the bounding box |
| `labelPosition` | `{x, y}`: where its label goes |
| `elements` | Native drawing-tool elements on a 100 x 100 grid (Excalidraw today) |
| `light`, `dark` | Per background: `file` (SVG path), `color`, and optionally `dataUrl` |

Place an icon by its centre, never its bounding box. A set without `center` is centred on
its main mass, the same way every time.

A project whose icons use another format can describe its own fields in the catalogue;
follow that.

## 3. Download

Lucide (ISC) or Tabler (MIT), through Iconify, coloured to the theme:

`https://api.iconify.design/lucide/<name>.svg?color=%23<hex>&height=96`

Use a light stroke on a dark background (for example `e9ecef`) and a dark one on a light
background (`1e1e1e`).

## 4. Shapes only

Cylinder, diamond, ellipse, cloud and the like, with a label.

## Record what was used

Where the project keeps its diagram conventions, list which icon sets were used, with
their licences.
