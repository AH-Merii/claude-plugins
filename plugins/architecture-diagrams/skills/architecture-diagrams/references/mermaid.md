# Fallback: Mermaid

Use Mermaid when no drawing tool is available, or when the diagram must live as text in a
repository or a page that renders Mermaid. Say once that this is the fallback, and what it
simplifies.

## What carries over

- **The form table and craft rules** still apply: one idea per diagram, about 15 elements,
  top to bottom for sequential diagrams, verbs on arrows, a legend.
- **Direction:** `flowchart TD` for flows, swimlanes and timelines; `LR` only for small
  relationship diagrams that would otherwise be tall and thin.
- **Theme:** start each diagram with an init block that sets the background and font, and
  define one `classDef` per element type with the theme's outline colour. Use the same class
  names in every diagram of the project.

  ```mermaid
  %%{init: {"theme": "base", "look": "handDrawn", "themeVariables": {"fontFamily": "Virgil, cursive"}}}%%
  flowchart TD
    classDef event stroke:#f08c00,stroke-width:2px
    classDef command stroke:#1971c2,stroke-width:2px
  ```

  `look: handDrawn` needs Mermaid 11 or newer; drop it where the renderer is older.
- **Icons:** where the renderer supports icon packs (Mermaid 11 `@{ icon: "..." }` nodes or
  `architecture-beta`), use the same icon names as the icon set. Otherwise put the icon's
  label in the node and say icons were dropped.
- **Links:** `click NodeId "https://..."` gives a node one link. Never put the same link in
  the label.
- **Legend:** a small `subgraph Legend` at the bottom, or a short list under the block.

## Forms

| Form | Mermaid |
| --- | --- |
| System context, containers | `flowchart TD` with a `subgraph` per owner, or `C4Context` |
| Swimlanes, event storming | `flowchart TD` with a `subgraph` per actor, steps in time order inside each |
| Flowchart | `flowchart TD` |
| Sequence | `sequenceDiagram` |
| State | `stateDiagram-v2` |
| Data flow | `flowchart TD`, stores as cylinders `[(name)]` |
| Context map | `flowchart TD`, one node per context, the relationship pattern as the edge label |
| Aggregates | `classDiagram`, invariants as a `note for` the root |
| Mind map | `mindmap` |
| 2x2 matrix | `quadrantChart` |
| Timeline | `flowchart TD` with dependencies as edges (`timeline` has none) |
| Decision table | A Markdown table, not Mermaid |

## Checking

Render the block (a Mermaid CLI or a preview) before showing it, and run the review
checklists on the render. A block that does not parse is not a diagram.
