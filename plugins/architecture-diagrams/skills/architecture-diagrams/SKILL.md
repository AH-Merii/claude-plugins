---
name: architecture-diagrams
description: How to choose and draw clear architecture and domain-driven design diagrams in one consistent, icon-first style, then review and publish them. Covers picking the form (system context, containers, event storming swimlanes, flowcharts, sequence, state, data flow, context maps, aggregates, decision tables, 2x2s, migration timelines, mind maps), craft rules, a vertical layout for scrolling, one link per element, a configurable hand-drawn theme, pluggable icon sets and drawing tools, reviewer passes, and putting snapshots on a page. Use when asked to draw, redraw, review or tidy any such diagram, whatever the drawing tool, with Mermaid as the fallback when there is none.
---

# Architecture diagrams

A diagram earns its place when it shows one idea a reader can take in at a glance and check
against its sources. This skill decides which form to draw, draws it in one consistent
style, checks it, and puts it where people will read it.

It assumes no project, drawing tool or icon set. Those come from the project profile (below)
and the adapters in `references/`. Without any of them it still works: default theme, a
downloaded icon set, and Mermaid if there is no drawing tool.

## Before the first diagram

1. **Read the project profile, if there is one.** Look for a "Diagrams" section in the
   project's CLAUDE.md, or a `diagrams.md` file at the project root or in its docs. It can
   set any of the keys in [Project profile](#project-profile). Anything it leaves out takes
   the default here.
2. **Pick the drawing tool.** Use the first that is available and say once which one is in
   use:
   - a canvas tool the session can write to, such as the Excalidraw+ connector: read its
     adapter first ([`references/excalidraw.md`](references/excalidraw.md));
   - another canvas or diagram tool: apply the same rules with its own tools, and note
     anything it cannot do (curved connectors, grouped icons, links on shapes);
   - none: Mermaid ([`references/mermaid.md`](references/mermaid.md)).
3. **Pick the icon source**, as [`references/icon-sets.md`](references/icon-sets.md)
   describes: the project's icon set, then a download, then plain shapes.
4. **Fix the theme.** Take the profile's values, or the defaults in [Theme](#theme), and
   reuse them exactly in every diagram of the project. If the project keeps a page or file
   of conventions, record them there with the first diagram.

## Existing diagrams are sources

Diagrams the user points to are read, never edited. Before drawing, check whether one
already shows what is needed:

- **Current:** link to it, and put a snapshot where it is needed, instead of redrawing it.
- **Partly right or out of date:** draw a new diagram based on it, and say what changed
  and why.

## Choosing the form

| What it must show | Form |
| --- | --- |
| Current-state and desired-state system context, containers | Icon-first architecture diagram, systems grouped by owner |
| Event storming; any process seen as who does what | Swimlanes: a column per actor headed by its icon, time top to bottom |
| A flow with decisions and branches | Flowchart, top to bottom |
| Systems talking to each other over time | Sequence diagram, one use case each |
| Where data lives and moves, who owns it | Data flow diagram, logical view first |
| Bounded contexts and how they relate | Context map: a shape per context with key terms and owning team, core ones emphasised, the relationship pattern on each arrow |
| Aggregates and their contents | Class-style boxes, invariants noted on the root |
| Lifecycle of one entity (an order, a refund) | State diagram, icon-first |
| How terms or drivers relate | Mind map, icon-first |
| Options compared for a decision | Table: options down, quality-attribute scenarios across, the recommended row marked |
| Two factors that dominate a choice; strengths and risks of an option | 2x2 matrix or SWOT |
| Migration path from current to desired state | Timeline, top to bottom, with dependencies |

Where two diagrams show the same thing, tell the user which is more informative, keep that
one and drop the other.

## Craft rules

- **One idea per diagram,** about 15 elements at most. Start high level and split for
  detail. A long flow stays one diagram; where it is published, show partial views of about
  six steps, each linking to the full diagram.
- **Lay out for scrolling.** Pages and phones scroll down, so sequential diagrams (event
  storming, flows, sequences, timelines) run top to bottom. Relationship diagrams (context
  map, system context, data flow) stay roughly square. Split anything wider than one screen,
  about 1,600 px.
- **Icon-first** for high-level and system design diagrams (context, containers, desired
  state): each element is a large icon (160 px by default) with no box around it, and under
  it its name, a one-line caption and a small bar in its category colour. Boxes only group.
- **Icons everywhere else too.** In every other diagram, each element the icon set covers
  shows its icon: full size where it stands alone (a state, a lane or participant header, a
  branch), and at least two thirds of that inside a box (110 px by default), so it reads at
  a glance. Size each box to its content.
- **Connectors join things.** A connector is a smooth curve from the edge of the shape it
  leaves to the edge of the shape it reaches, with no gap; beside an icon with no box it
  ends in a dot. Draw a light line over a thicker one in the source element's colour. Its
  label is a small rounded box on the line at the midpoint, so the line runs into it and
  out of it, never text floating beside. Branch or merge at a small circle. Allow about
  300 px between connected nodes and 80 px between others.
- **Label an arrow with what happens on it,** as a short verb (triggers, raises). No filler
  such as "then"; an arrow with nothing to say has no label.
- **One link per element.** Anything on a diagram that has its own page or record (a
  question, a finding, a decision, a glossary term, a ticket) links to it; never write a
  bare ID. Set each link once, on the shape (for an icon, on one of its elements), never
  also on its label, so every linked element shows exactly one link marker. Leave room for
  the marker at the top right. Linking is optional: draw without links when there is
  nothing to link to.
- **Every diagram has a legend** in a clear corner, naming each icon, shape, colour and
  line style it uses.
- **Status icons are consistent.** Where a step or state is planned, in progress, waiting,
  passed, failed, rework or a decision, use the icon set's icon for it, the same one
  everywhere.
- **No text under 16 px.**
- **No leftovers.** Before reporting, list the diagram's elements and delete your own that
  are empty, under 10 px or outside the diagram. Report any you did not add, and leave them.
- **Never describe a diagram that was not drawn.**

## Theme

Every diagram in a project uses one theme. Never mix styles. The default matches a
hand-drawn icon set; the project profile can change any value.

- **Shapes:** rounded corners on every shape, never hard squares; hand-drawn (rough)
  strokes of one width; the hand-drawn font throughout.
- **Colour:** one outline colour per element type, the same in every diagram and named in
  the legend. Take colours from the icon set's README where it defines them; otherwise use
  the DDD defaults below. Pick values that read on the chosen background.
- **Fill:** none, or a hachure in the outline's colour; the same choice for the same element
  type.
- **Background:** dark by default; light when the profile says so.
- **Alignment:** an icon sits over its caption, and arrows meet it, at its visual centre,
  not the middle of its bounding box. Take the centre from the icon set's manifest where
  it gives one; otherwise centre on the icon's main mass and use the same offset every time.

DDD element colours by default: domain event orange, command blue, policy violet,
aggregate yellow, read model green, hotspot red; a bounded context is neutral.

## Check before publishing

Render the diagram and compare it with the theme, the craft rules and the project's
approved examples, if the profile names any. Then, where the session can start subagents,
two fresh ones that did not draw it review it separately, as
[`references/review.md`](references/review.md) describes:

- a **style reviewer** checks the conventions, the layout and that each icon is the best
  fit;
- a **content reviewer** checks that it makes sense, repeats nothing, and matches the
  sources or records it rests on.

Without subagents, run both checklists yourself, one after the other, and say so. Fix what
they find, then show the diagram to the user.

## Publishing

The drawing tool's file is the single source of truth. Anywhere else a diagram appears
(a wiki page, a document, an issue) shows a snapshot that links back to it, as
[`references/publishing.md`](references/publishing.md) describes. In short: a
full-resolution image, a caption that links to the editable diagram with its date, and
snapshot and link replaced together in every edit.

## Privacy

- **New diagrams are private** unless the profile or the user names a shared place. Say
  where each one was saved.
- **Never create a public or share link on your own.** Make one only when the user asks for
  that diagram to be public, and note it where the diagram is published.
- **Draw only on diagrams you created.** Never edit a source diagram; copy it instead.
- **Brand and vendor icons** are for internal diagrams only.

## Project profile

A project sets any of these in the "Diagrams" section of its CLAUDE.md or in `diagrams.md`.
Each is optional.

| Key | What it sets | Default |
| --- | --- | --- |
| Drawing tool | The tool to use, and where new diagrams go (a collection, folder or board) | First available, private location |
| Icon set | Path or link to the icon set, and which of its libraries to use | Download (see icon-sets) |
| Custom icons | Icons for the project's own concepts, used before anything else for what they cover | None |
| Theme | Background, font, stroke style, colours per element type, icon sizes | The defaults above |
| Examples | Approved diagrams to match, as images or tool files | None |
| Publish to | Where snapshots go, and whether live embeds are allowed | Ask |
| Links | The record types diagrams link to (questions, decisions, tickets) | None |

Keep project-specific conventions (for example "an operator is drawn as a person and a
robot arm side by side") in the profile or the icon set's catalogue, never in this skill.
