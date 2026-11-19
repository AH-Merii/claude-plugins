# Adapter: Excalidraw+ connector

Read this when the session has the Excalidraw+ MCP connector. Tool names below are the
connector's at the time of writing; if a name has changed, match the tool by what it does.

## Where diagrams go

- **Draw every diagram as a new scene,** in the collection the project profile names, or
  the user's private collection by default. A new collection can be visible to the whole
  team: make one only when the user asks, and say who will see it.
- **Draw only on scenes you created.** Scenes the user points to are sources: read them
  with `get_scene_content` or `search_scene_content`, never write to them.
- **Moving a scene to another collection changes who sees it.** Do it only when the user
  says so, and say what becomes visible to whom.

## Drawing

- **Build every diagram by hand with `edit_scene_content`.** Do not use the generators
  (`create_diagram`, `create_mermaid_diagram`, `create_table`, `create_sticky_notes`):
  they cannot produce the theme.
- **Read the format guides first,** once per session: `read_freeform_format`, and
  `read_diagram_format` for swimlanes.
- **Every write returns `layoutIssues`.** Fix each one before going on; `check_scene_layout`
  re-checks.
- **Move, resize or repeat existing elements with `transform_elements`,** not by rewriting
  coordinates.
- **Labels inside shapes are the shape's label,** never a separate text element on top.
- **Links** go in the element's `link` field: on the shape, or on one element of an icon's
  group, never also on the label.

## Icons

- **Native icons** (an icon set whose manifest has Excalidraw elements): add the manifest
  entry's elements with `edit_scene_content`, translated so the entry's centre lands where
  the icon belongs and scaled if needed, all sharing one new `groupIds` value.
- **Image icons** (SVG files, data URLs, or an Iconify URL): place them with `add_image`.
- The connector cannot copy elements between scenes or import a `.excalidrawlib`. People
  editing by hand can add the icon set to their own Excalidraw library from its
  `.excalidrawlib` files; an agent does that only with browser tools and the user's yes.

## Checking

- Render with `take_screenshot`, or pass `screenshot: true` on a write.
- For the leftovers check, list the elements with `get_scene_content` and delete only the
  ones you added.

## Sharing

**Never call `share_scene` on your own.** It creates a link anyone can open without signing
in. Use it only when the user asks for that diagram to be public, and note it where the
diagram is published. For a scene that is already shared, pass its current access so an
edit link is not downgraded.

## Snapshots

For publishing, export the scene as SVG (dark or light to match the theme), or failing that
a full-resolution PNG. The connector's screenshot is too small for a page.
