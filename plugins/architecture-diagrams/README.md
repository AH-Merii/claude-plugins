# architecture-diagrams

A skill for drawing architecture and domain-driven design diagrams that read at a glance
and look the same across a project.

- **Choosing the form:** a table from what the diagram must show to its form: system
  context, event storming swimlanes, flowcharts, sequence, state, data flow, context maps,
  aggregates, decision tables, 2x2s, migration timelines and mind maps.
- **Craft rules:** one idea per diagram, top-to-bottom layout for anything sequential so it
  scrolls on a page or phone, icon-first elements, connectors that join edges with verb
  labels, one link per element, a legend, and no leftovers.
- **One theme:** hand-drawn and dark by default, with fixed colours per DDD element type.
  A project can change any value.
- **Review:** a style reviewer and a content reviewer, as fresh subagents where the
  session has them, before the user sees the diagram.
- **Publishing:** a full-resolution snapshot on the page with a caption that links back to
  the editable diagram, replaced together on every edit.

Nothing in it is tied to one project, drawing tool or icon set:

| Piece | Default | How to change it |
| --- | --- | --- |
| Drawing tool | Excalidraw+ connector if present, else any canvas tool, else Mermaid | `references/excalidraw.md` is one adapter; add another beside it |
| Icons | The project's icon set, then 29 built-in generic icons (Lucide, one recolourable SVG each), then Lucide or Tabler via Iconify, then plain shapes | Point the project settings at an icon set that follows `references/icon-sets.md` |
| Theme, examples, where diagrams and snapshots go | See SKILL.md | A "Diagrams" section in the project's CLAUDE.md, or a `diagrams.md` |

## Install

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install architecture-diagrams@ah-merii
```

The skill appears as `architecture-diagrams:architecture-diagrams`. Claude loads it when
asked to draw or review a diagram like these; you can also call it directly with
`/architecture-diagrams:architecture-diagrams`.

## Prerequisites

None. A drawing tool connector (such as Excalidraw+) and subagents make the results
better; without them it draws in Mermaid and reviews its own work.
