# Publishing a diagram on a page

The drawing tool's file is the single source of truth. A page, document or issue shows a
snapshot of it that links back. This holds whatever the page tool is: a wiki, a
document, an issue, or a Markdown file in a repository.

## Every time

- **Upload a snapshot as a file:** a vector image (SVG) in the theme's background, or
  failing that a full-resolution PNG. Never a tool's small preview screenshot.
- **Images there are usually not clickable, so the caption is the link:** "<name>: open the
  editable diagram", pointing at the diagram, plus the date it was drawn or last changed.
- **Replace snapshot and caption together** in the same step as every edit to the diagram,
  and correct the page text around it.
- **A redrawn diagram replaces the old one.** Once the new one is checked, repoint every
  snapshot and link to it, then delete the old diagram if you created it.
- **Upload images only to the page's own storage.** Never host an image elsewhere to embed
  it.

## Live embeds

Add a live embed instead of, or beside, the snapshot only when the diagram and the page are
both visible to the same people, and the user confirms it renders for them. An embed that
only its author can open shows everyone else an error.

## Markdown in a repository

Commit the SVG next to the page and link the editable diagram in the line under the image.
For a Mermaid diagram the code block is the source; no snapshot is needed.
