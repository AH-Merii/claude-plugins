---
name: conventional-commits
description: How to write commit messages and cut commits. Covers the Conventional Commits title (type, scope, behaviour-stating description, issue reference), a short body that explains what changed and why with sources, and one coherent change per commit, including tests-first pairs, mechanical splits and amending local follow-ups. Use when writing or rewording a commit message, deciding how to split, amend or order changes into commits, or tidying local history before review.
---

# Commit messages

A commit says what behaviour changed and why, in terms a reader can check without opening the diff. The title follows Conventional Commits. The body is short prose with sources.

## Title

- **`type(scope): description (#N)`.** Lowercase after the colon, no trailing period, and under about 72 characters.
- **Pick the type by what the commit does:**
  - `feat`: a new capability users can reach;
  - `fix`: behaviour corrected, including code brought in line with a newly enforced check;
  - `test`: tests only, including tests written before their implementation and fixes to tests;
  - `refactor`: structure changed, behaviour unchanged;
  - `style`: formatting only;
  - `docs`: documentation only;
  - `ci`: CI workflows and the check tasks they run;
  - `chore`: anything that ships nothing, such as assets or merging the base branch in.
- **The scope is the component the change is confined to,** such as a package, plugin or service. Leave it out when the change spans components or reorganises the repo: "style: format the whole repo with the project formatter".
- **The description states the behaviour, not the edit.** For a fix or a test, write the rule that now holds: "an edited input never gets a stale report", not "fix cache bug". Otherwise lead with a verb: "add", "split", "run".
- **End with the issue it serves, as `(#N)`.** It's the issue number, not the PR number that squash-merge titles add. Leave it off when there's no issue.

## Body

- **Say what changed, why, and any important decision.** Keep it succinct. When the cause or old state explains the change, start there ("load_entry was 14 against a complexity limit of 10."), then say what's true now.
- **Describe behaviour first.** Name functions or files only to help the reader find the change.
- **Link the decision it carries out.** When a recorded decision drives the commit, its first line is `Decision: <issue comment URL>`. The decision itself lives on the issue (see the writing-issues skill).
- **Claims carry sources inline:** a `path:line`, a quoted line of tool output or help text, a live run, or the upstream code the behaviour copies.
- **Say how it was checked when the tests don't show it:** "Checked live: <what ran and what it showed>". A mechanical commit says "No behaviour change."
- **Record what was dropped and why,** and who raised the change when review did ("Raised in code review.").
- **Use bullets for several independent changes and prose otherwise.** Wrap lines near 72 columns.
- **Skip the body only when the title says it all,** as in "drop a duplicate CSV header test".
- **No footers or trailers** beyond any the environment requires. The issue goes in the title and the decision link at the top of the body.

## Cutting commits

- **One coherent change per commit.** Each commit makes sense on its own. If a file holds unrelated changes, split it by hunk.
- **Mechanical changes stand alone.** Formatting, generated output, moves and docs-only edits each get their own commit, ahead of the semantic changes that depend on them.
- **Tests go with the behaviour they verify, except in tests-first work.** There, the test commit lands first and the implementing commit follows in the same PR, with matching titles (`test(x): <rule>`, then `fix(x): <rule>`).
- **Amend unpublished follow-ups into the commit they belong to.** Don't make tiny fixup commits. Once a commit is pushed, reviewed or shared, ask before rewriting it; otherwise add a new commit that says what prompted it.
- **Checkpoint commits are local savepoints.** When asked, tidy unpublished history (squash, reword, move changes) before review.
- **Commit only your own session's changes.** Leave other agents' work in a shared workspace alone.

PR titles and descriptions build on these rules; see the writing-prs skill. Examples are in [references/examples.md](references/examples.md).
