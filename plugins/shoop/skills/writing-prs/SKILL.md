---
name: writing-prs
description: How to write pull request titles and descriptions. Covers a commit-style title and a short prose description of what the PR does, how it was checked, the decisions a reviewer would question and what it leaves out, all linked to the issues it implements. Also covers keeping the description current and what stays out. Use when opening a PR, rewriting a PR description after the work changed, or checking whether a description gives a reviewer what they need.
---

# Writing pull requests

A PR description tells a reviewer what the PR does, why they can trust it, and what it deliberately doesn't do. The full record of decisions lives on the issues, and the description links to them.

The rules a PR shares with commit messages are in the conventional-commits skill: the title format, saying what changed and why with behaviour first, and inline sources. This skill covers what's different for a whole PR.

## Title

- **Use the commit title format without the `(#N)` suffix.** The type and scope describe the PR as a whole: "feat(cache): expire entries after a configurable TTL", "ci: run the unit tests on every PR".

## Description

- **Open with what the PR does, in a sentence or two.** Name the issues it implements inline, e.g. "(#41, #42, and the CLI part of #30)". When it implements only part of an issue, name that part.
- **With no issue behind it, open with the problem.** One paragraph on what goes wrong today, then what this PR adds.
- **Say how it was checked.** Give the command to rerun the tests and what they check against what, such as real tools in throwaway directories or a stand-in for an external service. Name any opt-in or live check and when it runs.
- **Give the decisions a reviewer would question, each with its reason:** "The whole suite runs on every PR, not just the tests for changed files, because…". When an issue comment records the decision, link it instead of repeating the whole record.
- **Say what it leaves out:** "Deliberately left out: …", known gaps and follow-ups, and the effect on existing users ("Installs are unaffected because…").
- **Name related PRs:** "Supersedes #50, which closed when its branch was renamed".
- **Say up front if it isn't meant to merge as is:** "This is an ideation PR: it is here to pick a direction, not to merge as is."
- **Write prose paragraphs, with bullets for parallel items.** Use no template headings such as Summary or Test plan.
- **Images go in when they show the point faster,** under the same sourcing rules as issue comments (writing-issues skill). Comparisons of several visual options go in comments, one per option.

## Keep it current

- **Describe the PR as it will merge, not its history.** When the PR changes, rewrite the lines that changed, for example when a tests-first PR gains its implementation ("Specifies the `export` command before it exists…" became "Adds the `export` command…").

## What stays out

- **No list of commits or files.** The commits carry their own messages.
- **No decision log.** Rejected options, measurements and corrections go on the issue as decision comments. The PR links to them.
- **Close fully implemented issues with keywords.** End the description with `Closes #N`, one line per issue the PR fully implements, so GitHub closes them on merge. Name an issue the PR only partly implements without a keyword; it stays open (writing-issues skill).

Example descriptions are in [references/examples.md](references/examples.md).
