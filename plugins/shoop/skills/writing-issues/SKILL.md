---
name: writing-issues
description: How to write GitHub issues and the comments that keep them accurate while the work changes them. Covers titles, the problem / decision / why body, dependency and "part of" lines, decision comments (decision, why, rejected), proposals, known limits, corrections and partly-done comments. Use when filing or splitting issues, recording a decision made while working on an issue, correcting or clarifying an earlier comment, or noting which part of an issue a merged PR covered.
---

# Writing issues

An issue is the one home for a piece of work and the decisions made on it. The body says what's wrong and what should be true. Comments record each decision that changes that, so the issue is still accurate when its PR lands. Decisions live in those comments, not in a separate decision-record file, and PRs and commits link to them.

## Title

- **Name the outcome in plain words.** Sentence case, no type prefix, no trailing period. A colon can introduce the parts, as in "Report export: CSV, JSON, and a stable column order".

## The body

- **Problem first.** Say what's wrong today and what it costs, concretely. Cite a real incident or measurement where there is one, e.g. "Two people reported wrong totals this way last week (#40, #44)."
- **Settled design: `## Problem`, `## Decision`, `## Why`.** Decision bullets have bold lead-ins, and each states a rule someone can check. Why gives the reasoning in a short paragraph.
- **Unsettled design: say what should be true, not how.** Describe the behaviour the work must deliver ("A rerun should always reflect the current input"). Put proposed implementation in the first comment, headed "Implementation notes" or "Proposed structure", with its open questions listed.
- **One idea per bullet, prose for the argument.** Bold lead-ins for parallel points; no templates, no acceptance-criteria checkboxes. The decision bullets are the criteria.
- **End with how it relates.** Use one short line for each: "Depends on #41", "Part of #30 (with #43)", "Being worked on in #57", "Related: #44 and #45".
- **One issue per outcome a PR can close.** A larger effort has its own issue; the parts point to it with "Part of".

## Decision comments

- **Comment when work changes what the issue should do:** scope, behaviour, or a rejected approach. Post it when it's decided, not at the end of the work.
- **Shape: decision, why, rejected.** Open with a bold title, `**Decision: <what>.**`, then the decision as bullets. **Why:** gives the evidence that forced it. **Rejected:** lists each alternative and the reason it lost. Add **Measured:** or **Risk:** where they apply.
- **Say where it was decided:** "while implementing (a1b2c3d)", "after code review", "measured on `main` at e4f5a6b".
- **Every claim carries a source.** Use a permalink pinned to a commit (`blob/<sha>/path#L64-L72`), a command with the relevant output, or a docs link. A SHA permalink survives later edits; a bare `path:line` doesn't.
- **Attach an image when it shows the point faster than text:** a screenshot or a before/after pair. Use a GIF only when the point is motion. Keep a text source alongside it. Uploads are public and can't be deleted, so never capture secrets.
- **Several decisions from one piece of work can share a comment,** with a heading each and the same decision / why / rejected shape under each.
- **Record a decision once, then point to it.** On another issue, link the comment instead of restating it: "The error format is recorded on #38: <comment url>".
- **Mark what isn't decided.** A proposal says so in its first line: "**Proposal, under discussion, not decided.** The issue body is unchanged."
- **Known limits are decisions too.** Open with "**Known limit, accepted by <who>:**", then give the case, what goes wrong, why it isn't handled (with evidence) and how it could be fixed.

## Corrections

- **Correct in a new comment, not by silently editing.** Open with what it corrects: "**Correction to the comment above.**", "Clarification: '<quote>' in the body is imprecise", or "replacing '<old rule>' from the earlier comment". Then give the revised decision, and put the old one under **Rejected:** with why it was wrong.
- **The body stays as filed while comments carry the changes.** Update it only once a decision has settled, and say so in that decision comment ("The issue body is updated to match").

## Closing

- **Done issues close through their PR.** The PR's `Closes #N` closes the issue on merge, so it needs no closing comment.
- **Partly done stays open, and says which part landed:** "The CLI part landed in #57 (merged as e4f5a6b): <what>. This issue stays open for <the rest>."

See [references/examples.md](references/examples.md) for a body, decision comments, a known limit, corrections and a partly-done comment.
